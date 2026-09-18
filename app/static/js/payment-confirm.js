(() => {
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.matches("[data-payment-confirm]")) return;

    if (form.dataset.paymentOwnerOnly !== undefined) {
      const payer = form.querySelector('input[name="payer"]:checked');
      if (!payer || payer.value !== "owner") return;
    }

    const label = form.dataset.paymentLabel || "UMSHADO access";
    const amount = form.dataset.paymentAmount || "0.00";
    const phone = form.dataset.paymentPhone || "your registered phone";
    const confirmed = window.confirm(
      `You are about to request a MoMo payment of E${amount} for ${label}.\n\n` +
      `The request will be sent to ${phone}. Access applies only to this wedding project.\n\nContinue?`
    );
    if (!confirmed) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    const confirmation = form.querySelector('input[name="payment_confirmed"]');
    if (confirmation) confirmation.value = "yes";
  }, true);
})();
