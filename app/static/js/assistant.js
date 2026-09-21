(() => {
  const launcher = document.getElementById("assistant-launcher");
  const panel = document.getElementById("assistant-panel");
  const closeButton = document.getElementById("assistant-close");
  const form = document.getElementById("assistant-form");
  const input = document.getElementById("assistant-input");
  const messages = document.getElementById("assistant-messages");
  const clearButton = document.getElementById("assistant-clear");
  const suggestions = document.getElementById("assistant-suggestions");
  if (!launcher || !panel || !form || !input || !messages) return;

  let history = [];
  let busy = false;

  const open = () => {
    panel.hidden = false;
    launcher.setAttribute("aria-expanded", "true");
    window.setTimeout(() => input.focus(), 30);
  };
  const close = () => {
    panel.hidden = true;
    launcher.setAttribute("aria-expanded", "false");
    launcher.focus();
  };
  const scrollToLatest = () => {
    messages.scrollTop = messages.scrollHeight;
  };
  const addMessage = (content, role) => {
    const element = document.createElement("div");
    element.className = `assistant-message assistant-message-${role}`;
    element.textContent = content;
    messages.appendChild(element);
    scrollToLatest();
    return element;
  };
  const setBusy = (value) => {
    busy = value;
    input.disabled = value;
    form.querySelector("button[type='submit']").disabled = value;
  };
  const readJson = async (response) => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "The assistant could not complete that request.");
    return data;
  };

  const addConfirmation = (confirmation) => {
    const card = document.createElement("div");
    card.className = "assistant-confirmation";
    const summary = document.createElement("p");
    summary.textContent = confirmation.summary;
    const note = document.createElement("small");
    note.textContent = `This confirmation expires in ${confirmation.expires_in_minutes} minutes.`;
    const actions = document.createElement("div");
    const confirm = document.createElement("button");
    confirm.className = "button primary";
    confirm.type = "button";
    confirm.textContent = confirmation.confirm_label || "Confirm change";
    const cancel = document.createElement("button");
    cancel.className = "button secondary";
    cancel.type = "button";
    cancel.textContent = "Cancel";
    actions.append(confirm, cancel);
    card.append(summary, note, actions);
    messages.appendChild(card);
    scrollToLatest();

    cancel.addEventListener("click", () => {
      card.remove();
      addMessage("The proposed change was cancelled.", "bot");
    });
    confirm.addEventListener("click", async () => {
      confirm.disabled = true;
      cancel.disabled = true;
      confirm.textContent = "Saving…";
      try {
        const response = await fetch(form.dataset.confirmUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": form.dataset.csrfToken,
          },
          body: JSON.stringify({token: confirmation.token}),
        });
        const data = await readJson(response);
        card.remove();
        addMessage(data.reply, "bot");
        history.push({role: "assistant", content: data.reply});
      } catch (error) {
        confirm.disabled = false;
        cancel.disabled = false;
        confirm.textContent = confirmation.confirm_label || "Confirm change";
        addMessage(error.message, "error");
      }
    });
  };

  const send = async (message) => {
    const content = message.trim();
    if (!content || busy) return;
    const priorHistory = history.slice(-8);
    addMessage(content, "user");
    history.push({role: "user", content});
    input.value = "";
    suggestions.hidden = true;
    setBusy(true);
    const loading = addMessage("Thinking…", "loading");
    try {
      const response = await fetch(form.dataset.messageUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": form.dataset.csrfToken,
        },
        body: JSON.stringify({message: content, history: priorHistory}),
      });
      const data = await readJson(response);
      loading.remove();
      addMessage(data.reply, "bot");
      history.push({role: "assistant", content: data.reply});
      if (data.confirmation) addConfirmation(data.confirmation);
    } catch (error) {
      loading.remove();
      addMessage(error.message, "error");
    } finally {
      setBusy(false);
      input.focus();
    }
  };

  launcher.addEventListener("click", () => panel.hidden ? open() : close());
  closeButton.addEventListener("click", close);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    send(input.value);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  suggestions.addEventListener("click", (event) => {
    const button = event.target.closest("[data-assistant-prompt]");
    if (button) send(button.dataset.assistantPrompt);
  });
  clearButton.addEventListener("click", () => {
    history = [];
    messages.replaceChildren();
    addMessage("Chat cleared. How can I help with your wedding project?", "bot");
    suggestions.hidden = false;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) close();
  });
})();
