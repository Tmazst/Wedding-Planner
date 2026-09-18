(() => {
  document.addEventListener("click", (event) => {
    const selectable = event.target.closest("[data-select-on-click]");
    if (selectable instanceof HTMLInputElement) selectable.select();
    if (event.target.closest("[data-print]")) window.print();
    if (event.target.closest("[data-reload]")) window.location.reload();
  });
})();
