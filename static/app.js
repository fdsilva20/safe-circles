// Register the service worker for offline access to the toolkit.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('/static/sw.js', { scope: '/' }).then(function (reg) {
      var note = document.getElementById('offline-note');
      if (note && location.pathname.indexOf('/toolkit') === 0) { note.hidden = false; }
    }).catch(function () { /* offline support is optional */ });
  });
}
