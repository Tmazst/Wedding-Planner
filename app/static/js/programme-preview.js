(() => {
  const form = document.querySelector('[data-programme-settings]');
  const cards = [...document.querySelectorAll('[data-programme-card]')];

  const ensureSelectedFont = async () => {
    if (!form || !document.fonts) return;
    const font = form.elements.font_style?.value || 'elegant';
    const face = font === 'elegant' ? "'Great Vibes'" : font === 'romantic' ? "'Allura'" : null;
    if (!face) return;
    try {
      await document.fonts.load(`29px ${face}`);
      await document.fonts.ready;
    } catch (_) {
      // The CSS fallback remains available if the font request fails.
    }
  };

  const apply = () => {
    if (!form || !cards.length) return;
    const template = form.elements.template_key?.value || 'floral_elegant';
    const font = form.elements.font_style?.value || 'elegant';
    const primary = form.elements.primary_color?.value || '#7d1020';
    const accent = form.elements.accent_color?.value || '#b88a3b';

    cards.forEach((card) => {
      [...card.classList].forEach((name) => {
        if (name.startsWith('template-') || name.startsWith('font-')) card.classList.remove(name);
      });
      card.classList.add(`template-${template}`, `font-${font}`);
      card.dataset.fontStyle = font;
      card.style.setProperty('--programme-primary', primary);
      card.style.setProperty('--programme-accent', accent);

      const title = card.querySelector('[data-preview-title]');
      const closing = card.querySelector('[data-preview-closing]');
      const photo = card.querySelector('.programme-couple-photo');
      if (title) title.textContent = form.elements.title?.value.trim() || 'Wedding Programme';
      if (closing) closing.textContent = form.elements.closing_message?.value.trim() || 'For being part of our special day.';
      if (photo) photo.hidden = !form.elements.show_profile_image?.checked;
    });
  };

  if (form) {
    form.addEventListener('input', apply);
    form.addEventListener('change', async () => {
      apply();
      await ensureSelectedFont();
      apply();
    });
    apply();
  }

  const openButton = document.querySelector('[data-programme-preview-open]');
  const modal = document.querySelector('[data-programme-preview-modal]');
  const closeButton = document.querySelector('[data-programme-preview-close]');

  const setOpen = async (open) => {
    if (!modal || !openButton) return;
    if (open) {
      apply();
      await ensureSelectedFont();
      apply();
    }
    modal.classList.toggle('is-open', open);
    modal.setAttribute('aria-hidden', open ? 'false' : 'true');
    openButton.setAttribute('aria-expanded', open ? 'true' : 'false');
    document.body.style.overflow = open ? 'hidden' : '';
    if (open) closeButton?.focus();
  };

  openButton?.addEventListener('click', () => setOpen(true));
  closeButton?.addEventListener('click', () => setOpen(false));
  modal?.addEventListener('click', (event) => {
    if (event.target === modal) setOpen(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && modal?.classList.contains('is-open')) setOpen(false);
  });
})();
