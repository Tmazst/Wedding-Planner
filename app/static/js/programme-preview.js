(() => {
  const form = document.querySelector('[data-programme-settings]');
  const card = document.querySelector('[data-programme-card]');
  if (!form || !card) return;

  const title = card.querySelector('[data-preview-title]');
  const closing = card.querySelector('[data-preview-closing]');
  const photo = card.querySelector('.programme-couple-photo');

  const apply = () => {
    const template = form.elements.template_key?.value || 'floral_elegant';
    const font = form.elements.font_style?.value || 'elegant';
    const primary = form.elements.primary_color?.value || '#7d1020';
    const accent = form.elements.accent_color?.value || '#b88a3b';

    [...card.classList].forEach((name) => {
      if (name.startsWith('template-') || name.startsWith('font-')) card.classList.remove(name);
    });
    card.classList.add(`template-${template}`, `font-${font}`);
    card.style.setProperty('--programme-primary', primary);
    card.style.setProperty('--programme-accent', accent);

    if (title) title.textContent = form.elements.title?.value.trim() || 'Wedding Programme';
    if (closing) closing.textContent = form.elements.closing_message?.value.trim() || 'For being part of our special day.';
    if (photo) photo.hidden = !form.elements.show_profile_image?.checked;
  };

  form.addEventListener('input', apply);
  form.addEventListener('change', apply);
  apply();
})();
