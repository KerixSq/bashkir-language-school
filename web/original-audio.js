'use strict';
// Original licensed source audio; deliberately separate from synthesized TTS.
window.OriginalAudio = (() => {
  const region = document.getElementById('web-original-audio');
  const button = document.getElementById('original-audio-play');
  const note = document.getElementById('original-audio-status');
  const audio = document.getElementById('original-audio-player');
  let segment = null;
  let ticket = 0;
  let stopTimer;
  function pause() {
    clearTimeout(stopTimer);
    audio.pause();
    button.textContent = 'Слушать оригинал';
    button.setAttribute('aria-pressed', 'false');
  }
  function clear() {
    ticket++;
    segment = null;
    pause();
    audio.removeAttribute('src');
    audio.load();
    region.hidden = true;
    note.textContent = '';
  }
  function setTask(task) {
    clear();
    if (!task || task.source_kind !== 'audio' || task.time_start == null || task.time_end == null) return;
    const start = Number(task.time_start), end = Number(task.time_end);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start) return;
    if (typeof task.source_url !== 'string' || !/^\/web\/assets\/original-audio\/[0-9a-f]{64}\.(wav|mp3)$/.test(task.source_url)) return;
    segment = {start, end, label: `${task.source || 'Исходное аудио'} · ${start}–${end} с. ${task.source_license || ''}`};
    audio.src = task.source_url;
    region.hidden = false;
    note.textContent = segment.label;
  }
  audio.addEventListener('loadedmetadata', () => {
    if (!segment) return;
    if (segment.end > audio.duration + 0.05) {
      pause();
      note.textContent = 'Таймкоды выходят за пределы записи. Текстовое задание доступно.';
      button.disabled = true;
    } else audio.currentTime = segment.start;
  });
  audio.addEventListener('timeupdate', () => {
    if (segment && !audio.paused && audio.currentTime >= segment.end) {
      pause();
      audio.currentTime = segment.end;
    }
  });
  audio.addEventListener('error', () => {
    if (segment) {
      pause();
      note.textContent = 'Не удалось загрузить оригинал. Можно повторить или продолжить текстовое задание.';
    }
  });
  button.addEventListener('click', async () => {
    if (!segment) return;
    if (!audio.paused) { pause(); return; }
    const current = ticket;
    window.BashkirTTS?.stop();
    try {
      if (audio.error) audio.load();
      if (audio.readyState >= 1) audio.currentTime = segment.start;
      await audio.play();
      if (current !== ticket) return;
      button.textContent = 'Остановить оригинал';
      note.textContent = segment.label;
      button.setAttribute('aria-pressed', 'true');
      stopTimer = setTimeout(() => { if (current === ticket) pause(); }, Math.max(0, segment.end - audio.currentTime) * 1000);
    } catch (_) {
      if (current === ticket) note.textContent = 'Не удалось воспроизвести оригинал. Повтори попытку; текстовое задание доступно.';
    }
  });
  document.addEventListener('click', event => {
    if (event.target.closest('#web-tts, #game-tts, #game-start')) pause();
  }, true);
  document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); });
  window.addEventListener('pagehide', pause);
  audio.addEventListener('ended', pause);
  return {clear, pause, setTask(task) { button.disabled = false; setTask(task); }};
})();
