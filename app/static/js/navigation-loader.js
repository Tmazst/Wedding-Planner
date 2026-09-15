(() => {
  const loader = document.getElementById("page-loader");
  if (!loader) return;

  let revealTimer;
  const show = () => {
    clearTimeout(revealTimer);
    revealTimer = setTimeout(() => {
      loader.hidden = false;
      document.body.classList.add("is-loading");
    }, 120);
  };
  const hide = () => {
    clearTimeout(revealTimer);
    loader.hidden = true;
    document.body.classList.remove("is-loading");
  };

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.dataset.noLoader !== undefined) return;
    const submitter = event.submitter;
    if (submitter && submitter.dataset.noLoader !== undefined) return;
    show();
  });

  document.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest("a[href]");
    if (!link || link.dataset.noLoader !== undefined || link.hasAttribute("download") || link.target === "_blank") return;
    const url = new URL(link.href, window.location.href);
    if (url.origin !== window.location.origin || url.protocol !== window.location.protocol) return;
    if (url.pathname === window.location.pathname && url.search === window.location.search && url.hash) return;
    show();
  });

  window.addEventListener("pageshow", hide);
  window.addEventListener("beforeunload", () => {
    clearTimeout(revealTimer);
    loader.hidden = false;
  });
})();
