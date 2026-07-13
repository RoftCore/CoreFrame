(function() {
  var EXT_ID = 'my_extension';

  function wait() {
    if (typeof extensionsData !== 'undefined' && extensionsData[EXT_ID]) {
      init();
      return;
    }
    setTimeout(wait, 200);
  }

  function init() {
    console.log('[EXT] ' + EXT_ID + ' loaded');
  }

  wait();
})();
