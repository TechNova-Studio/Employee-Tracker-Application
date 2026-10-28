export const API_BASE =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

export function getToken() {
  return localStorage.getItem("workpulse_token") || "";
}

export function normalizeRows(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;
  return [];
}

//hnerfcefbvhjbjfvbefhvbjfvbfhvbfhvbfhvbhfbvhfbvkhffbhdfvbc hbehifhfbfer fhubhfhi beqkudfhbf asfh sbdf djhvbsd jh fdvejh fvbefuyfvbdksfb weuhbdsfc ukwhjdbvuk jsdhbdvcu shd sb fvcuhysdjfbcuhgbdfcehbrssfdgberhfbdchubafhudebchjbasdhcvehudcgbu d bfvbuqf vjqyhfgbjhcfjgcviuekag fbiugyefuyegbfcuqefakcgkuldghcukw ejfhci ekhf hjwev rfcbiwdgcbuegbciqewhgfbuqi ewwdgfveyqedfveydfvyegdfcvyedvcygedvcjhevardsdfchjvbeasdckj gwbduycxihg wabskud j gweuf gff gedif gedyufgqewkaghsd oqweiughwioehfqewugfqeoirgf oeirhfioerygf iurfgeieq kyagfiu3gfo iyewgfoeirfh oeirhfi ieruhfir fh8iyg r ygr8ou irferoui hryg h 8oih o9 iuefhqeroiu rr yiehi fureioh 3re8dih rfudihre8ifh 34r3ieh8 iure8uoi  rr8 uir eriyihje rfdsyihr edihr edifer fohor ukrehfiukrehdiu

function errorText(data, fallback) {
  if (typeof data === "string") return data;
  if (Array.isArray(data))
    return data.map((item) => errorText(item, fallback)).join(" ");
  if (!data || typeof data !== "object") return fallback;
  for (const key of ["detail", "reason", "blocked_reason"])
    if (data[key]) return errorText(data[key], fallback);
  return (
    Object.entries(data)
      .filter(([key]) => key !== "raw")
      .map(
        ([key, value]) =>
          `${key.replaceAll("_", " ")}: ${errorText(value, fallback)}`,
      )
      .join(" • ") || fallback
  );
}

export async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData))
    headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers.Authorization = `Token ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!res.ok)
    throw new Error(errorText(data, `Request failed (${res.status}).`));
  return data;
}

export async function screenshotBlob(id, action = "view", signal) {
  const res = await fetch(`${API_BASE}/screenshots/${id}/${action}/`, {
    headers: { Authorization: `Token ${getToken()}` },
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let data;
    try {
      data = await res.json();
    } catch {
      data = {};
    }
    throw new Error(errorText(data, `Screenshot unavailable (${res.status}).`));
  }
  const blob = await res.blob();
  if (!["image/png", "image/jpeg", "image/webp"].includes(blob.type))
    throw new Error("The stored file is not a supported image.");
  return blob;
}

export function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function protectedBlob(pathOrUrl, filename) {
  const url = pathOrUrl.startsWith("http")
    ? pathOrUrl
    : `${API_BASE}${pathOrUrl}`;
  const res = await fetch(url, {
    headers: { Authorization: `Token ${getToken()}` },
  });
  if (!res.ok) throw new Error(await res.text());
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  if (filename) {
    const a = document.createElement("a");
    a.href = href;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } else {
    window.open(href, "_blank");
  }
  setTimeout(() => URL.revokeObjectURL(href), 5000);
}

export function saveLogin(data) {
  localStorage.setItem("workpulse_token", data.token);
  localStorage.setItem("workpulse_user", JSON.stringify(data.user || {}));
}

export function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem("workpulse_user") || "{}");
  } catch {
    return {};
  }
}
