// Tu lógica JavaScript aquí

async function initMyExtension() {
  // Inicialización
  const data = await apiFetch('/api/extension/my_extension/my_action');
  if (data.error) return;
  console.log('My extension data:', data);
}

// Auto-init
(function waitForInit() {
  if (typeof extensionsData !== 'undefined' && Object.keys(extensionsData).length) {
    initMyExtension();
    return;
  }
  setTimeout(waitForInit, 200);
})();
