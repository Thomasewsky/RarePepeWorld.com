(function () {
  'use strict';

  var storageKey = 'rpw-card-mosaic-transition';
  var svgNamespace = 'http://www.w3.org/2000/svg';
  var busy = false;

  function motionIsReduced() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function mosaicAnimationSupported() {
    return typeof window.requestAnimationFrame === 'function' && typeof Element !== 'undefined' &&
      Element.prototype && typeof Element.prototype.animate === 'function' && typeof Promise !== 'undefined';
  }

  function navigateWithoutMosaic(url, mosaic) {
    if (mosaic && mosaic.svg) mosaic.svg.remove();
    document.documentElement.classList.remove('rpw-transition-entering');
    try { sessionStorage.removeItem(storageKey); } catch (ignore) {}
    busy = false;
    window.location.assign(url);
  }

  function makeMosaic(mode) {
    var width = Math.max(1, window.innerWidth);
    var height = Math.max(1, window.innerHeight);
    var columns = Math.max(8, Math.min(16, Math.ceil(width / 105)));
    var rows = Math.ceil(height / (width / columns));
    var cellWidth = width / columns;
    var cellHeight = height / rows;
    var svg = document.createElementNS(svgNamespace, 'svg');
    svg.setAttribute('class', 'rpw-mosaic-overlay');
    svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.setAttribute('aria-hidden', 'true');

    var tiles = [];
    for (var row = 0; row < rows; row += 1) {
      for (var column = 0; column < columns; column += 1) {
        var x1 = column * cellWidth;
        var x2 = (column + 1) * cellWidth;
        var y1 = row * cellHeight;
        var y2 = (row + 1) * cellHeight;
        var flip = (row + column) % 2 === 1;
        var triangles = flip
          ? [[x1, y1, x2, y1, x1, y2], [x2, y1, x2, y2, x1, y2]]
          : [[x1, y1, x2, y1, x2, y2], [x1, y1, x2, y2, x1, y2]];

        triangles.forEach(function (coordinates, triangleIndex) {
          var polygon = document.createElementNS(svgNamespace, 'polygon');
          polygon.setAttribute('points', coordinates[0] + ',' + coordinates[1] + ' ' +
            coordinates[2] + ',' + coordinates[3] + ' ' +
            coordinates[4] + ',' + coordinates[5]);
          var horizontalStep = mode === 'cover' ? 8.5 : 10.5;
          var delay = (columns - 1 - column) * horizontalStep + row * 1.25 + triangleIndex * 0.5;
          polygon.style.opacity = mode === 'cover' ? '0' : '1';
          if (mode === 'cover') polygon.style.transform = 'scale(.78)';
          polygon.dataset.stagger = String(delay);
          svg.appendChild(polygon);
          tiles.push(polygon);
        });
      }
    }
    document.body.appendChild(svg);
    return { svg: svg, tiles: tiles, mode: mode };
  }

  function animateMosaic(mosaic) {
    var revealing = mosaic.mode === 'reveal';
    var duration = revealing ? 300 : 255;
    var animations = mosaic.tiles.map(function (tile) {
      var delay = Number(tile.dataset.stagger) || 0;
      return tile.animate(
        revealing
          ? [{ opacity: 1, transform: 'scale(1)' }, { opacity: 0, transform: 'scale(.86)' }]
          : [{ opacity: 0, transform: 'scale(.78)' }, { opacity: 1, transform: 'scale(1)' }],
        { duration: duration, delay: delay, easing: 'cubic-bezier(.2,.68,.24,1)', fill: 'both' }
      );
    });
    return Promise.all(animations.map(function (animation) {
      return animation.finished.catch(function () {});
    }));
  }

  function startReveal() {
    var mosaic;
    try {
      mosaic = makeMosaic('reveal');
      document.documentElement.classList.remove('rpw-transition-entering');
      window.__rpwCardTransitionPhase = 'reveal';
      requestAnimationFrame(function () {
        try {
          animateMosaic(mosaic).then(function () {
            mosaic.svg.remove();
            window.__rpwCardTransitionPhase = 'revealed';
          }).catch(function () {
            mosaic.svg.remove();
            window.__rpwCardTransitionPhase = 'revealed';
          });
        } catch (ignore) {
          mosaic.svg.remove();
          window.__rpwCardTransitionPhase = 'revealed';
        }
      });
    } catch (ignore) {
      document.documentElement.classList.remove('rpw-transition-entering');
      if (mosaic && mosaic.svg) mosaic.svg.remove();
      try { sessionStorage.removeItem(storageKey); } catch (ignoreStorage) {}
    }
  }

  function normalPath(path) {
    return path.replace(/\/$/, '') || '/';
  }

  function internalPageDestination(link) {
    if (!link || link.hasAttribute('download') || link.hasAttribute('data-no-transition') ||
        link.getAttribute('role') === 'button' || link.closest('form') ||
        link.matches('.detail-original-link')) return null;
    var target = (link.getAttribute('target') || '').toLowerCase();
    if (target && target !== '_self') return null;
    if (link.relList && link.relList.contains('external')) return null;
    try {
      var destination = new URL(link.href, window.location.href);
      if (destination.origin !== window.location.origin || !/^https?:$/.test(destination.protocol)) return null;
      if (/\.(?:avif|bmp|css|csv|docx?|gif|ico|jpe?g|js|json|pdf|png|svg|txt|webp|zip)$/i.test(destination.pathname) ||
          /\/static\/artwork_cache\//i.test(destination.pathname)) return null;
      if (/\/(?:invoice|B28vk)\/?$/i.test(destination.pathname)) return null;
      if (normalPath(destination.pathname) === normalPath(window.location.pathname) &&
          destination.search === window.location.search) return null;
      return destination;
    } catch (ignore) {
      return null;
    }
  }

  function beginInternalNavigation(event, link) {
    if (busy || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey ||
        event.shiftKey || event.altKey || motionIsReduced() || !mosaicAnimationSupported()) return;
    var destination = internalPageDestination(link);
    if (!destination) return;

    event.preventDefault();
    busy = true;
    try {
      sessionStorage.setItem(storageKey, JSON.stringify({ url: destination.href, started: Date.now() }));
    } catch (ignore) {
      window.location.assign(destination.href);
      return;
    }

    var mosaic;
    try {
      mosaic = makeMosaic('cover');
      window.__rpwCardTransitionPhase = 'cover';
      requestAnimationFrame(function () {
        try {
          animateMosaic(mosaic).then(function () {
            window.__rpwCardTransitionPhase = 'navigate';
            window.location.assign(destination.href);
          }).catch(function () {
            navigateWithoutMosaic(destination.href, mosaic);
          });
        } catch (ignore) {
          navigateWithoutMosaic(destination.href, mosaic);
        }
      });
    } catch (ignore) {
      navigateWithoutMosaic(destination.href, mosaic);
    }
  }

  function isArchiveSearchForm(form) {
    if (!form || form.tagName !== 'FORM' || (form.method || '').toLowerCase() !== 'post') return false;
    var target = (form.getAttribute('target') || '').toLowerCase();
    if (target && target !== '_self') return false;
    try {
      var action = new URL(form.action, window.location.href);
      return action.origin === window.location.origin && normalPath(action.pathname) === '/search';
    } catch (ignore) {
      return false;
    }
  }

  function submitSearchWithMosaic(event, form) {
    if (busy || event.defaultPrevented || motionIsReduced() || !mosaicAnimationSupported()) return;

    var mosaic;
    try {
      sessionStorage.setItem(storageKey, JSON.stringify({
        url: window.location.origin + '/',
        anyPath: true,
        started: Date.now()
      }));
      mosaic = makeMosaic('cover');
    } catch (ignore) {
      try { sessionStorage.removeItem(storageKey); } catch (ignoreStorage) {}
      if (mosaic && mosaic.svg) mosaic.svg.remove();
      return;
    }

    event.preventDefault();
    busy = true;
    window.__rpwCardTransitionPhase = 'cover';
    requestAnimationFrame(function () {
      try {
        animateMosaic(mosaic).then(function () {
          window.__rpwCardTransitionPhase = 'navigate';
          HTMLFormElement.prototype.submit.call(form);
        }).catch(function () {
          mosaic.svg.remove();
          try { sessionStorage.removeItem(storageKey); } catch (ignoreStorage) {}
          busy = false;
          HTMLFormElement.prototype.submit.call(form);
        });
      } catch (ignore) {
        mosaic.svg.remove();
        try { sessionStorage.removeItem(storageKey); } catch (ignoreStorage) {}
        busy = false;
        HTMLFormElement.prototype.submit.call(form);
      }
    });
  }

  if (!motionIsReduced() && mosaicAnimationSupported() &&
      document.documentElement.classList.contains('rpw-transition-entering')) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', startReveal, { once: true });
    } else {
      startReveal();
    }
  } else if (!mosaicAnimationSupported()) {
    document.documentElement.classList.remove('rpw-transition-entering');
    try { sessionStorage.removeItem(storageKey); } catch (ignore) {}
  }

  document.addEventListener('click', function (event) {
    var target = event.target;
    var link = target && target.closest ? target.closest('a[href]') : null;
    if (link) beginInternalNavigation(event, link);
  });

  document.addEventListener('submit', function (event) {
    var form = event.target;
    if (isArchiveSearchForm(form)) submitSearchWithMosaic(event, form);
  }, true);

  window.addEventListener('pageshow', function (event) {
    if (event.persisted) {
      document.documentElement.classList.remove('rpw-transition-entering');
      var staleOverlay = document.querySelector('.rpw-mosaic-overlay');
      if (staleOverlay) staleOverlay.remove();
      busy = false;
    }
  });
})();
