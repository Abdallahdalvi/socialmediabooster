// Preload script for Electron
const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('electron', {
  version: () => process.versions.electron,
});
