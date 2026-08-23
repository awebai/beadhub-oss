(function () {
  'use strict';

  var eventName = 'BeadHub Activation';
  var storageKey = 'beadhub_activation_site_visit';

  window.plausible = window.plausible || function () {
    (window.plausible.q = window.plausible.q || []).push(arguments);
  };

  if (!window.beadhubAnalyticsEnabled) return;

  try {
    if (window.sessionStorage.getItem(storageKey)) return;
    window.sessionStorage.setItem(storageKey, '1');
  } catch (_error) {
    // Storage may be disabled. A duplicate visit is preferable to breaking the site.
  }

  window.plausible(eventName, {
    props: {
      step: 'visit',
      surface: 'site'
    },
    interactive: false
  });
})();
