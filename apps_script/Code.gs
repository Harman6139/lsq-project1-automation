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

    deleteNames.forEach(function(item) {
      const deleteName = typeof item === 'string' ? item : item.name;
      const deleteFolderPath = typeof item === 'string' ? '' : (item.folderPath || '');
      const deleteFolder = getOrCreateFolderPath(folder, deleteFolderPath);
      trashByName(deleteFolder, deleteName);
    });

    files.forEach(function(file) {
      const targetFolder = getOrCreateFolderPath(folder, file.folderPath || '');
      trashByName(targetFolder, file.name);

      const bytes = Utilities.base64Decode(file.contentBase64);
      const blob = Utilities.newBlob(bytes, file.mimeType || 'application/octet-stream', file.name);
      const created = targetFolder.createFile(blob).setName(file.name);
      results.push({ folderPath: file.folderPath || '', name: file.name, id: created.getId(), url: created.getUrl() });
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
  if (!name) {
    return;
  }
  const existing = folder.getFilesByName(name);
  while (existing.hasNext()) {
    existing.next().setTrashed(true);
  }
}

function getOrCreateFolderPath(rootFolder, folderPath) {
  if (!folderPath) {
    return rootFolder;
  }

  let current = rootFolder;
  const parts = folderPath.split('/').map(function(part) {
    return part.trim();
  }).filter(function(part) {
    return part.length > 0;
  });

  parts.forEach(function(part) {
    const matches = current.getFoldersByName(part);
    current = matches.hasNext() ? matches.next() : current.createFolder(part);
  });

  return current;
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
