const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function request(path, options) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch {
    throw new Error("Could not reach CloudVault. Check that the backend is running.");
  }

  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // Keep the HTTP status message when the server does not return JSON.
    }
    throw new Error(message);
  }

  return response;
}

export async function listFiles() {
  const response = await request("/files");
  return response.json();
}

export async function uploadFile(file, onProgress) {
  return new Promise((resolve, reject) => {
    const body = new FormData();
    body.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/upload`);
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

      try {
        resolve(JSON.parse(xhr.responseText));
      } catch {
        reject(new Error("The server returned an invalid upload response."));
      }
    });
    xhr.addEventListener("error", () => {
      reject(new Error("Could not reach CloudVault. Check that the backend is running."));
    });
    xhr.addEventListener("abort", () => reject(new Error("Upload was cancelled.")));
    xhr.send(body);
  });
}

export async function deleteFile(id) {
  await request(`/files/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function downloadFile(id, filename) {
  const response = await request(`/download/${encodeURIComponent(id)}`);
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
