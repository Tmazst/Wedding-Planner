(() => {
  const form = document.querySelector('[data-invitation-settings]');
  const cards = [...document.querySelectorAll('[data-invitation-card]')];

  const apply = () => {
    if (!form || !cards.length) return;
    const template = form.elements.template_key?.value || 'floral_elegant';
    const font = form.elements.font_style?.value || 'elegant';
    const primary = form.elements.primary_color?.value || '#7d1020';
    const accent = form.elements.accent_color?.value || '#b88a3b';
    const message = form.elements.message?.value.trim() || 'Request the pleasure of your company as they celebrate their wedding day.';
    const showPhoto = Boolean(form.elements.show_profile_image?.checked);

    cards.forEach((card) => {
      [...card.classList].forEach((name) => {
        if (name.startsWith('template-') || name.startsWith('font-')) card.classList.remove(name);
      });
      card.classList.add(`template-${template}`, `font-${font}`);
      card.style.setProperty('--invitation-primary', primary);
      card.style.setProperty('--invitation-accent', accent);
      const messageNode = card.querySelector('[data-invitation-message]');
      if (messageNode) messageNode.textContent = message;
      const photo = card.querySelector('.invitation-photo');
      if (photo) photo.hidden = !showPhoto;
    });
  };

  form?.addEventListener('input', apply);
  form?.addEventListener('change', apply);
  apply();

  const modal = document.querySelector('[data-invitation-preview-modal]');
  const openButton = document.querySelector('[data-invitation-preview-open]');
  const closeButton = document.querySelector('[data-invitation-preview-close]');
  const open = () => {
    if (!modal) return;
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    openButton?.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
  };
  const close = () => {
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    openButton?.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
  };
  openButton?.addEventListener('click', open);
  closeButton?.addEventListener('click', close);
  modal?.addEventListener('click', (event) => { if (event.target === modal) close(); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') close(); });
})();
