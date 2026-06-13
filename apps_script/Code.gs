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
    const deleteFolders = payload.deleteFolders || [];

    deleteNames.forEach(function(item) {
      const deleteName = typeof item === 'string' ? item : item.name;
      const deleteFolderPath = typeof item === 'string' ? '' : (item.folderPath || '');
      const deleteFolder = getFolderPath(folder, deleteFolderPath);
      if (deleteFolder) {
        trashByName(deleteFolder, deleteName);
      }
    });

    deleteFolders.forEach(function(folderPath) {
      trashFolderPath(folder, folderPath);
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

function trashFolderPath(rootFolder, folderPath) {
  if (!folderPath) {
    return;
  }

  const parts = cleanPathParts(folderPath);
  if (parts.length === 0) {
    return;
  }

  let parent = rootFolder;
  for (let i = 0; i < parts.length - 1; i++) {
    const matches = parent.getFoldersByName(parts[i]);
    if (!matches.hasNext()) {
      return;
    }
    parent = matches.next();
  }

  const targets = parent.getFoldersByName(parts[parts.length - 1]);
  while (targets.hasNext()) {
    targets.next().setTrashed(true);
  }
}

function getFolderPath(rootFolder, folderPath) {
  if (!folderPath) {
    return rootFolder;
  }

  let current = rootFolder;
  const parts = cleanPathParts(folderPath);
  for (let i = 0; i < parts.length; i++) {
    const matches = current.getFoldersByName(parts[i]);
    if (!matches.hasNext()) {
      return null;
    }
    current = matches.next();
  }

  return current;
}

function getOrCreateFolderPath(rootFolder, folderPath) {
  if (!folderPath) {
    return rootFolder;
  }

  let current = rootFolder;
  const parts = cleanPathParts(folderPath);

  parts.forEach(function(part) {
    const matches = current.getFoldersByName(part);
    current = matches.hasNext() ? matches.next() : current.createFolder(part);
  });

  return current;
}

function cleanPathParts(folderPath) {
  return String(folderPath).split('/').map(function(part) {
    return part.trim();
  }).filter(function(part) {
    return part.length > 0;
  });
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
