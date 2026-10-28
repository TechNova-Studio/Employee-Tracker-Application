import base64
import hashlib
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone
from rest_framework.authtoken.models import Token
from .models import Company, Profile, ERPConnector, ERPEmployeeMapping, CRMLoginAttempt, AgentVersion


class CRMSSOTests(TestCase):
    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name='SSO company')
        self.user = User.objects.create_user(username='mapped')
        Profile.objects.create(user=self.user, company=self.company, role='EMPLOYEE')
        self.connector = ERPConnector.objects.create(company=self.company, name='CRM', api_token='server-only')
        ERPEmployeeMapping.objects.create(connector=self.connector, external_id='GLUTAPE0079', user=self.user)
        self.config = {'glutape': dict(name='Glutape', authorization_url='https://crm.example/authorize',
            token_url='https://crm.example/token', userinfo_url='https://crm.example/me',
            client_id='desktop', connector_id=self.connector.pk, crm_company_id='7', issuer='https://crm.example')}
        override = override_settings(CRM_SSO_PROVIDERS=self.config)
        override.enable(); self.addCleanup(override.disable)
        self.verifier = 'a' * 43
        self.challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).decode().rstrip('=')
        self.identity = dict(external_id='GLUTAPE0079', company_id='7', is_active=True,
                             issuer='https://crm.example', audience='desktop')

    def start(self, **extra):
        return self.client.post('/api/auth/crm/start/', dict(provider='glutape', redirect_uri='http://127.0.0.1:45678/crm/callback',
            state='s'*43, code_challenge=self.challenge) | extra, content_type='application/json')

    def payload(self):
        response = self.start()
        self.assertEqual(response.status_code, 200)
        return dict(attempt_token=response.json()['attempt_token'], code='one-use-code', code_verifier=self.verifier,
                    app_version='1.0.0', platform='windows')

    def exchange(self, payload=None, identity=None):
        payload = payload or self.payload()
        with patch('core.crm_sso.crm_json', side_effect=[{'access_token': 'private', 'token_type': 'Bearer'},
                                                        identity if identity is not None else self.identity]) as crm:
            response = self.client.post('/api/auth/crm/exchange/', payload, content_type='application/json')
        return response, crm

    def test_success_reuses_mapping_and_keeps_credentials_private(self):
        payload = self.payload()
        attempt = CRMLoginAttempt.objects.get()
        self.assertNotEqual(attempt.secret_hash, payload['attempt_token'])
        response, crm = self.exchange(payload)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['user']['id'], self.user.pk)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(crm.call_args_list[0].args[1]['code_verifier'], self.verifier)
        self.assertEqual(crm.call_args_list[1].kwargs['bearer'], 'private')
        self.assertNotIn('private', str(response.content))
        replay, crm = self.exchange(payload)
        self.assertEqual(replay.status_code, 403); crm.assert_not_called()

    def test_bad_verifier_and_expiry_never_contact_crm(self):
        payload = self.payload(); payload['code_verifier'] = 'b'*43
        response, crm = self.exchange(payload)
        self.assertEqual(response.status_code, 403); crm.assert_not_called()
        CRMLoginAttempt.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        payload['code_verifier'] = self.verifier
        response, crm = self.exchange(payload)
        self.assertEqual(response.status_code, 403); crm.assert_not_called()

    def test_missing_mapping_does_not_create_user(self):
        response, _ = self.exchange(identity={**self.identity, 'external_id':'unknown'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['blocked_reason'], 'MAPPING_REQUIRED')
        self.assertEqual(User.objects.count(), 1); self.assertFalse(Token.objects.exists())

    def test_identity_scope_and_inactive_rejected(self):
        for field, value in [('company_id','8'), ('is_active',False), ('is_active','true'), ('issuer','https://evil.example'), ('audience','other')]:
            with self.subTest(field=field):
                response, _ = self.exchange(identity={**self.identity, field:value})
                self.assertEqual(response.status_code, 403)
        self.assertFalse(Token.objects.exists())

    def test_missing_workpulse_profile_is_rejected_without_issuing_token(self):
        self.user.profile.delete()
        response, _ = self.exchange()
        self.assertEqual(response.status_code, 403)
        self.assertIn('Mapped WorkPulse employee is inactive', response.json()['detail'])
        self.assertTrue(ERPEmployeeMapping.objects.filter(user=self.user).exists())
        self.assertFalse(Token.objects.exists())

    def test_success_token_can_register_desktop_device(self):
        response, _ = self.exchange()
        self.assertEqual(response.status_code, 200, response.content)
        registered = self.client.post('/api/agent/device/register/', {
            'device_id': 'crm-sso-test-device', 'hostname': 'SSO desktop',
            'platform': 'windows', 'app_version': '1.0.0',
        }, content_type='application/json',
            HTTP_AUTHORIZATION='Token ' + response.json()['token'])
        self.assertEqual(registered.status_code, 200, registered.content)
        from .models import Device
        device = Device.objects.get(device_id='crm-sso-test-device')
        self.assertEqual(device.user_id, self.user.pk)
        self.assertEqual(device.company_id, self.company.pk)

    def test_workpulse_inactive_and_foreign_profile_rejected(self):
        self.user.is_active = False; self.user.save()
        self.assertEqual(self.exchange()[0].status_code,403)
        self.user.is_active = True; self.user.save()
        profile = self.user.profile
        profile.company = Company.objects.create(name='other'); profile.save()
        self.assertEqual(self.exchange()[0].status_code,403)
        self.assertFalse(Token.objects.exists())

    def test_company_policy_and_version_gates(self):
        self.company.status = 'SUSPENDED'; self.company.save()
        self.assertEqual(self.exchange()[0].status_code,403)
        self.company.status = 'ACTIVE'; self.company.save()
        profile = self.user.profile; profile.policy_status = 'POLICY_DECLINED'; profile.save()
        self.assertEqual(self.exchange()[0].status_code,403)
        profile.policy_status = 'PENDING'; profile.save()
        AgentVersion.objects.create(platform='windows',latest_version='2.0.0',minimum_supported_version='2.0.0',is_active=True)
        response, _ = self.exchange()
        self.assertEqual(response.status_code,426)
        self.assertFalse(Token.objects.exists())

    def test_callback_and_provider_validation(self):
        for redirect in ('http://evil.example:123/crm/callback','http://127.0.0.1:123/other',
                         'http://127.0.0.1:123/crm/callback?x=1','http://user@127.0.0.1:123/crm/callback'):
            self.assertEqual(self.start(redirect_uri=redirect).status_code,400)
        result = self.client.get('/api/auth/crm/providers/').json()
        self.assertEqual(result, {'providers':[{'id':'glutape','name':'Glutape'}]})
        self.assertNotIn('server-only',str(result))
        self.connector.is_active=False; self.connector.save()
        self.assertEqual(self.client.get('/api/auth/crm/providers/').json()['providers'],[])
        self.assertEqual(self.start().status_code,403)

    def test_upstream_failure_consumes_handshake_without_issuing_token(self):
        from rest_framework.exceptions import APIException
        payload=self.payload()
        with patch('core.crm_sso.crm_json',side_effect=APIException('unavailable')):
            response=self.client.post('/api/auth/crm/exchange/',payload,content_type='application/json')
        self.assertEqual(response.status_code,500)
        self.assertIsNotNone(CRMLoginAttempt.objects.get().used_at)
        self.assertFalse(Token.objects.exists())

    def test_malformed_json_and_token_response(self):
        response=self.client.post('/api/auth/crm/start/', [], content_type='application/json')
        self.assertEqual(response.status_code,400)
        payload=self.payload()
        with patch('core.crm_sso.crm_json',return_value={'token_type':123,'access_token':'bad'}):
            response=self.client.post('/api/auth/crm/exchange/',payload,content_type='application/json')
        self.assertEqual(response.status_code,403)
        self.assertFalse(Token.objects.exists())

    def test_crm_network_errors_are_sanitized(self):
        from urllib.error import URLError
        from core.crm_sso import crm_json
        with patch('core.crm_sso.build_opener') as opener:
            opener.return_value.open.side_effect=URLError('secret details')
            from rest_framework.exceptions import APIException
            with self.assertRaises(APIException) as error:
                crm_json('https://crm.example/token', {'code':'private-code'})
            self.assertEqual(error.exception.status_code,502)
            self.assertNotIn('secret details',str(error.exception))

    def test_cleanup_deletes_only_old_expired_attempts(self):
        from django.core.management import call_command
        self.payload()
        fresh=CRMLoginAttempt.objects.get()
        CRMLoginAttempt.objects.create(secret_hash='f'*64,provider='glutape',challenge=self.challenge,
            redirect_uri=fresh.redirect_uri,expires_at=timezone.now()-timedelta(days=2))
        call_command('cleanup_crm_logins')
        self.assertEqual(list(CRMLoginAttempt.objects.values_list('pk',flat=True)),[fresh.pk])
        self.assertEqual(ERPEmployeeMapping.objects.count(),1)
