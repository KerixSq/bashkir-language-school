/* Section navigation shares the existing openTab action; no API operations here. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const items = [...document.querySelectorAll('[data-app-dest]')];
  const context = byId('sidebar-context');
  const tabNav = byId('sections-nav');
  let current = 'learn';
  let frame = 0;
  const sections = [
    ['.quest-hero', 'learn'], ['.path-preview', 'lessons'],
    ['#web-profile-area', 'practice'], ['#game-zone', 'lessons'],
    ['.community-quest', 'library'], ['#game-console', 'lessons'],
    ['.game-achievements', 'rewards'], ['#sections-nav', 'tab'],
  ].map(([selector, dest]) => ({node: document.querySelector(selector), dest}));
  const selectedTab = () => tabNav.querySelector('[aria-selected="true"]')?.dataset.view || 'ratings';
  const value = id => byId(id)?.textContent.trim() || '—';
  const copy = {
    learn: ['С Акбузатом по Уралу', 'Один урок — пять заданий на фразах корпуса.', 'Начать урок'],
    lessons: ['Твоя тренировка', '', 'Продолжить урок'],
    practice: ['Проверяем вместе', '', 'К заданию'],
    ratings: ['Результаты сообщества', '', 'К участникам'],
    translations: ['База переводов', 'Итоги согласования с источниками. Доступны поиск и экспорт.', 'К переводам'],
    rewards: ['Коллекция путешественника', '', 'Открыть коллекцию'],
    library: ['Библиотека Акбузата', '', 'Посмотреть переводы'],
    teacher: ['Для преподавателя', 'Отчёт класса и CSV доступны по коду преподавателя.', 'К отчёту'],
    expert: ['Решение эксперта', 'Сходство помогает сравнить варианты. Итог выбирает человек.', 'К спорным случаям'],
    about: ['О платформе', 'Источники, правила и ограничения проверки переводов.', 'Подробнее'],
    api: ['Открытые результаты', 'REST API и экспорт согласованных переводов.', 'К API'],
  };
  function render() {
    const [title, description, action] = copy[current] || copy.learn;
    let detail = description;
    if (current === 'lessons') detail = `${value('game-console-title')} · ${value('game-score')} тренировочных XP. Сохраняются в этом браузере.`;
    if (current === 'practice') detail = document.body.dataset.serverSession === 'true'
      ? `${value('web-points')} серверных очков. Проверь вариант или предложи исправление.`
      : 'Войди с никнеймом, чтобы проверять переводы. Тренировочные XP учитываются отдельно.';
    if (current === 'library') detail = value('community-confirmed') === '—'
      ? 'Число согласованных переводов пока недоступно. Подключение можно проверить в настройках.'
      : `${value('community-confirmed')} согласованных переводов · ${byId('community-pair').selectedOptions[0].textContent}.`;
    if (current === 'rewards') detail = `${document.querySelectorAll('#game-badges .game-badge:not(.locked)').length} из ${byId('game-badges').children.length} наград за тренировку в этом браузере.`;
    if (current === 'ratings') detail = `Период: ${document.querySelector('[data-period][aria-pressed="true"]')?.textContent || 'день'}. Участники, классы и школы — в таблицах ниже.`;
    context.dataset.section = current;
    byId('sidebar-context-title').textContent = title;
    byId('sidebar-context-detail').textContent = detail;
    byId('sidebar-context-action').textContent = action;
  }
  function active(dest) {
    current = dest;
    items.forEach(item => {
      const mobile = item.closest('.app-mobile-nav');
      const group = mobile ? '.app-mobile-nav' : '.app-sidebar';
      const represented = document.querySelector(`${group} [data-app-dest="${dest}"]`);
      const match = item.dataset.appDest === (represented ? dest : 'learn');
      item.classList.toggle('is-active', match);
      if (match) item.setAttribute('aria-current', 'location');
      else item.removeAttribute('aria-current');
    });
    render();
  }
  function measure() {
    frame = 0;
    if (document.body.classList.contains('lesson-active')) return active('lessons');
    // A short tab can end before its header reaches the activation band.
    if (tabNav.getBoundingClientRect().top < innerHeight &&
        scrollY + innerHeight >= document.documentElement.scrollHeight - 2) return active(selectedTab());
    const line = innerHeight * 0.25;
    const candidates = sections.filter(({node}) => node?.getClientRects().length)
      .map(entry => ({...entry, top: entry.node.getBoundingClientRect().top}));
    const passed = candidates.filter(entry => entry.top <= line + 1).sort((a,b) => b.top - a.top);
    const dest = (passed[0] || candidates[0])?.dest || 'learn';
    active(dest === 'tab' ? selectedTab() : dest);
  }
  function schedule() { if (!frame) frame = requestAnimationFrame(measure); }
  // Only section boundaries are observed. Hidden tabpanels never enter scrollspy.
  const observer = new IntersectionObserver(schedule, {rootMargin: '0px 0px -75% 0px', threshold: 0});
  sections.forEach(({node}) => { if (node) observer.observe(node); });
  const resize = new ResizeObserver(schedule);
  resize.observe(document.querySelector('main'));
  addEventListener('resize', schedule);
  addEventListener('pageshow', schedule);
  addEventListener('hashchange', schedule);
  document.addEventListener('section-tab-changed', schedule);
  items.forEach(item => item.addEventListener('click', () => {
    active(item.dataset.appDest);
    schedule();
  }));
  byId('play-entry').addEventListener('click', event => {
    event.preventDefault();
    active('lessons');
    byId('path-stage-1').click();
  });
  byId('sidebar-context-action').addEventListener('click', () => {
    if (current === 'learn' || current === 'lessons') return byId('game-start').click();
    if (current === 'library') return document.querySelector('.app-sidebar [data-open-tab="translations"]').click();
    const target = current === 'practice' ? byId('web-profile-area')
      : current === 'rewards' ? byId('game-badges') : tabNav;
    target.scrollIntoView({behavior: 'auto', block: 'start'});
    if (current === 'library') return;
    if (current !== 'practice' && current !== 'rewards') byId(`tab-${current}`)?.focus();
  });
  // Refresh text from rendered data, never invent unknown server statistics.
  const dataObserver = new MutationObserver(render);
  ['game-score','game-console-title','game-badges','community-confirmed','web-points'].forEach(id => {
    dataObserver.observe(byId(id), {childList:true, subtree:true, characterData:true});
  });
  new MutationObserver(() => {render();schedule();}).observe(document.body, {attributes:true, attributeFilter:['data-server-session','class']});
  new MutationObserver(render).observe(byId('ratings'), {attributes:true, subtree:true, attributeFilter:['aria-pressed']});
  active('learn');
  schedule();
})();
