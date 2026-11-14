/* Section navigation shares the existing openTab action; no API operations here. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const items = [...document.querySelectorAll('[data-app-dest]')];
  const context = byId('sidebar-context');
  const tabNav = byId('sections-nav');
  let current = null;
  let region = null;
  let travel = null;
  let hold = null;
  const hysteresis = 12;
  let frame = 0;
  const sections = [
    ['.quest-hero', 'learn'], ['.path-preview', 'lessons'],
    ['#web-profile-area', 'practice'], ['#game-zone', 'lessons'],
    ['.community-quest', 'library'], ['.game-console-main', 'lessons'],
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
    if (context.dataset.section !== current) context.dataset.section = current;
    if (byId('sidebar-context-title').textContent !== title) byId('sidebar-context-title').textContent = title;
    if (byId('sidebar-context-detail').textContent !== detail) byId('sidebar-context-detail').textContent = detail;
    if (byId('sidebar-context-action').textContent !== action) byId('sidebar-context-action').textContent = action;
  }
  function active(dest) {
    if (current === dest) return;
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
  function regions() {
    const consoleNode = document.querySelector('.game-console-main');
    const consoleRect = consoleNode.getBoundingClientRect();
    return sections.filter(({node}) => {
      if (!node?.getClientRects().length) return false;
      // Desktop achievements share a row with the lesson. That row belongs to
      // lessons while scrolling; an explicit achievements click still selects it.
      const rect = node.getBoundingClientRect();
      return !node.matches('.game-achievements') || rect.left < consoleRect.right ||
        Math.abs(rect.top-consoleRect.top) > 48;
    }).map(entry => ({...entry, top:entry.node.getBoundingClientRect().top+scrollY}))
      .sort((a,b) => a.top-b.top);
  }
  function measure() {
    frame = 0;
    if (document.body.classList.contains('lesson-active')) return active('lessons');
    if (travel) {
      const end = Math.max(0, Math.min(document.documentElement.scrollHeight-innerHeight,
        travel.target.getBoundingClientRect().top+scrollY-16));
      active(travel.dest);
      if (Math.abs(scrollY-end) <= 2 || performance.now()-travel.started > 3000) {
        hold = {dest:travel.dest, top:scrollY};
        travel = null;
      } else schedule();
      return;
    }
    if (hold && Math.abs(scrollY-hold.top) <= 2) return;
    hold = null;
    const list = regions();
    const line = scrollY+innerHeight*.25;
    let index = 0;
    list.forEach((entry,i) => { if (entry.top <= line) index = i; });
    if (tabNav.getBoundingClientRect().top < innerHeight &&
        scrollY+innerHeight >= document.documentElement.scrollHeight-2) index = list.length-1;
    const old = list.findIndex(entry => entry.node === region);
    if (old >= 0 && index !== old) {
      if (index > old && line < list[index].top+hysteresis) index = old;
      if (index < old && line > list[old].top-hysteresis) index = old;
    }
    region = list[index].node;
    active(list[index].dest === 'tab' ? selectedTab() : list[index].dest);
  }
  function schedule() { if (!frame) frame = requestAnimationFrame(measure); }
  function interrupt() {
    if (travel) scrollTo({top:scrollY,behavior:'instant'});
    travel = hold = null;
    schedule();
  }
  function navigate(dest) {
    const target = dest === 'learn' ? document.querySelector('.quest-hero')
      : dest === 'lessons' ? byId('game-zone') : dest === 'practice' ? byId('web-profile-area')
      : dest === 'library' ? document.querySelector('.community-quest')
      : dest === 'rewards' ? document.querySelector('.game-achievements') : tabNav;
    if (travel) scrollTo({top:scrollY,behavior:'instant'});
    hold = null;
    travel = {dest,target,started:performance.now()};
    active(dest);
    const top = target.getBoundingClientRect().top+scrollY-16;
    scrollTo({top:Math.max(0,top),behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'instant':'smooth'});
    schedule();
  }
  window.BashkirNavigation = {navigate};
  // One passive document scroll listener and at most one frame; no competing
  // IntersectionObservers or independent click-only navigation state.
  addEventListener('scroll', schedule, {passive:true});
  addEventListener('wheel', interrupt, {passive:true});
  addEventListener('touchstart', interrupt, {passive:true});
  addEventListener('pointerdown', event => {
    if (!event.target.closest('[data-app-dest],#sections-nav,#sidebar-context')) interrupt();
  }, {passive:true});
  addEventListener('keydown', event => {
    if (['ArrowUp','ArrowDown','PageUp','PageDown','Home','End',' '].includes(event.key) &&
        !event.target.closest('input,textarea,select,button')) interrupt();
  });
  const resize = new ResizeObserver(() => { hold = null; schedule(); });
  resize.observe(document.querySelector('main'));
  addEventListener('resize', schedule);
  addEventListener('pageshow', schedule);
  addEventListener('hashchange', interrupt);
  document.addEventListener('section-tab-changed', () => {
    if (tabNav.getBoundingClientRect().top < innerHeight) {
      const dest = selectedTab();
      if (travel) travel.dest = dest;
      hold = {dest,top:scrollY};
      active(dest);
    }
    schedule();
  });
  items.forEach(item => item.addEventListener('click', event => {
    if (item.dataset.openTab) return; // Existing handler opens tab then calls navigate.
    event.preventDefault();
    navigate(item.dataset.appDest);
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
