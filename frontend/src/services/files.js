// Same-origin Vercel deployments already expose the API under /api.
// Keep the base empty so endpoint paths are not duplicated as /api/api/...
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function request(path, options) {
  let response;
  try {
    const headers = new Headers(options?.headers);
    headers.set("X-Requested-With", "XMLHttpRequest");
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      credentials: "include",
    });
  } catch {
    throw new Error("Could not reach CloudVault. Check that the backend is running.");
  }

  if (!response.ok) {
    if (response.status === 401 && path !== "/api/auth/login") {
      window.dispatchEvent(new Event("cloudvault:session-expired"));
    }
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) {
        message = body.detail
          .map((item) => item?.msg)
          .filter(Boolean)
          .join(" ") || message;
      }
    } catch {
      // Keep the HTTP status message when the server does not return JSON.
    }
    throw new Error(message);
  }

  return response;
}

export async function getAuthStatus() {
  const response = await request("/api/auth/status");
  return response.json();
}

export async function login(email, password) {
  const response = await request("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return response.json();
}

export async function register(email, password) {
  const response = await request("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return response.json();
}

export async function logout() {
  await request("/api/auth/logout", { method: "POST" });
}

export async function listFiles() {
  const response = await request("/api/files");
  return response.json();
}

export async function getStorageStatus() {
  const response = await request("/api/storage/status");
  return response.json();
}

export async function uploadFile(file, onProgress, storageBackend) {
  if (!["local", "github", "s3"].includes(storageBackend)) {
    throw new Error("The storage backend is not ready yet.");
  }
  if (storageBackend === "local" || storageBackend === "github") {
    const body = new FormData();
    body.append("file", file);
    const responseText = await sendFile(`${API_BASE}/api/files`, {
      method: "POST",
      headers: { "X-Requested-With": "XMLHttpRequest" },
      body,
      withCredentials: true,
      onProgress,
      errorMessage: "Could not reach CloudVault. Check that the backend is running.",
    });
    try {
      return JSON.parse(responseText);
    } catch {
      throw new Error("The server returned an invalid upload response.");
    }
  }

  const response = await request("/api/uploads/presign", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: file.name,
      size: file.size,
      content_type: file.type || "application/octet-stream",
    }),
  });
  const upload = await response.json();

  await sendFile(upload.upload_url, {
    method: "PUT",
    headers: upload.headers,
    body: file,
    onProgress,
    errorMessage: "Could not upload the file to S3. Check the bucket CORS configuration.",
  });
  const completed = await request(`/api/uploads/${encodeURIComponent(upload.id)}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ size: file.size }),
  });
  return completed.json();
}

function sendFile(url, { method, headers, body, withCredentials = false, onProgress, errorMessage }) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    xhr.withCredentials = withCredentials;
    for (const [name, value] of Object.entries(headers)) xhr.setRequestHeader(name, value);
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        onProgress?.(event.loaded, event.total);
      }
    });
    xhr.addEventListener("load", () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        let message = `Request failed (${xhr.status}).`;
        try {
          const response = JSON.parse(xhr.responseText);
          if (typeof response.detail === "string") message = response.detail;
        } catch {
          // Keep the HTTP status message when the server does not return JSON.
        }
        reject(new Error(message));
        return;
      }

      resolve(xhr.responseText);
    });
    xhr.addEventListener("error", () => {
      reject(new Error(errorMessage));
    });
    xhr.addEventListener("abort", () => reject(new Error("Upload was cancelled.")));
    xhr.send(body);
  });
}

export async function deleteFile(id) {
  await request(`/api/files/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function downloadFile(id, filename, storageBackend) {
  let url;
  if (storageBackend === "s3") {
    const response = await request(`/api/files/${encodeURIComponent(id)}/download-url`);
    ({ url } = await response.json());
  } else {
    const response = await request(`/api/files/${encodeURIComponent(id)}/download`);
    url = URL.createObjectURL(await response.blob());
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
}
