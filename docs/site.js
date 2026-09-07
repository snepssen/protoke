/* The face demo and the copy buttons. Nothing here draws a face from scratch:
   the frames in face-loop.js are the renderer's own geometry, exported from
   the Python that writes the subtitle tracks. A second implementation in
   JavaScript would drift from the first the moment either one changed. */

(function face() {
  const canvas = document.getElementById('faceCanvas');
  const toggle = document.getElementById('faceToggle');
  const status = document.getElementById('faceStatus');
  if (!canvas || !toggle) return;

  const ctx = canvas.getContext('2d');
  let loop = null, at = 0, timer = null;

  function colour() {
    /* Deliberately not --signal. The stage stands in for black video output,
       where the renderer draws this colour whatever the visitor's OS theme
       is; following the theme would dim the face on a light desktop and
       misrepresent what the tool actually produces. */
    const ink = getComputedStyle(document.documentElement)
      .getPropertyValue('--face').trim();
    return ink || '#FFD400';
  }

  function draw() {
    if (!loop) return;
    const frame = loop.frames[at % loop.frames.length];
    at += 1;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    /* The face is authored in units where 1000 is its nominal height; fit it
       to whichever drawing buffer the canvas was given. */
    const scale = canvas.height / (loop.unit * 0.72);
    const tint = colour();
    ctx.save();
    ctx.translate(canvas.width / 2, canvas.height / 2);
    ctx.translate((frame.o[0] || 0) * scale, (frame.o[1] || 0) * scale);
    if (frame.t) ctx.rotate(frame.t * Math.PI / 180);
    ctx.fillStyle = tint;
    ctx.shadowColor = tint;
    ctx.shadowBlur = 26;
    for (const shape of frame.s) {
      ctx.beginPath();
      for (let i = 0; i < shape.length; i += 2) {
        const x = shape[i] * scale, y = shape[i + 1] * scale;
        if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      }
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }

  function stop() {
    clearInterval(timer);
    timer = null;
    toggle.dataset.playing = 'false';
    toggle.textContent = 'Play the face';
  }

  function start() {
    if (!loop) {
      loop = window.FACE_LOOP;
      if (!loop) {
        status.textContent = 'The face frames could not be loaded.';
        return;
      }
      status.textContent =
        `${loop.frames.length} frames · ${loop.frames[0].s.length} shapes · one loop`;
    }
    timer = setInterval(draw, 1000 / (loop.fps || 20));
    toggle.dataset.playing = 'true';
    toggle.textContent = 'Stop';
  }

  toggle.addEventListener('click', () => {
    if (toggle.dataset.playing === 'true') stop(); else start();
  });

  /* A hidden tab should not keep animating. */
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && toggle.dataset.playing === 'true') stop();
  });

  /* Draw one resting frame so the stage is never an empty box. */
  loop = window.FACE_LOOP || null;
  if (loop) {
    draw();
    at = 0;
    status.textContent =
      `${loop.frames.length} frames · ${loop.frames[0].s.length} shapes · one loop`;
  }
})();

(function copyButtons() {
  for (const button of document.querySelectorAll('.copy')) {
    button.addEventListener('click', async () => {
      const text = button.dataset.copy || '';
      try {
        await navigator.clipboard.writeText(text);
        button.dataset.state = 'done';
        button.textContent = 'Copied';
      } catch (error) {
        /* Clipboard access can be refused; say so rather than lying. */
        button.textContent = 'Select it';
        return;
      }
      setTimeout(() => {
        delete button.dataset.state;
        button.textContent = 'Copy';
      }, 1600);
    });
  }
})();
