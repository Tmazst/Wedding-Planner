(() => {
  const button = document.getElementById("photo-edit");
  const input = document.getElementById("photo-upload");
  const form = document.getElementById("photo-form");
  if (!button || !input || !form) return;
  button.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    if (input.files && input.files.length) form.requestSubmit();
  });
})();
