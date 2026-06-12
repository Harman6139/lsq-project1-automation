const FOLDER_ID = '1MgFc1OMXcFoTzDgcfpae1n_cKhDuDOzq';
const UPLOAD_SECRET = 'PASTE_UPLOAD_SECRET_HERE';

function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents);
    if (payload.secret !== UPLOAD_SECRET) {
      return jsonResponse({ ok: false, error: 'Unauthorized' });
    }

    const folder = DriveApp.getFolderById(FOLDER_ID);
    const results = [];
    const files = payload.files || [];
    const deleteNames = payload.deleteNames || [];

    deleteNames.forEach(function(name) {
      trashByName(folder, name);
    });

    files.forEach(function(file) {
      trashByName(folder, file.name);

      const bytes = Utilities.base64Decode(file.contentBase64);
      const blob = Utilities.newBlob(bytes, file.mimeType || 'application/octet-stream', file.name);
      const created = folder.createFile(blob).setName(file.name);
      results.push({ name: file.name, id: created.getId(), url: created.getUrl() });
    });

    return jsonResponse({ ok: true, results: results });
  } catch (err) {
    return jsonResponse({ ok: false, error: String(err) });
  }
}

function doGet() {
  return jsonResponse({ ok: true, message: 'LSQ monthly upload endpoint is active.' });
}

function trashByName(folder, name) {
  const existing = folder.getFilesByName(name);
  while (existing.hasNext()) {
    existing.next().setTrashed(true);
  }
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
