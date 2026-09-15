(() => {
  if (typeof window.io !== "function") return;

  const status = document.getElementById("connection-status");
  const onlineTeam = document.getElementById("online-team");
  const feed = document.getElementById("activity-feed");
  const socket = window.io("/planning", { transports: ["websocket", "polling"] });

  const setStatus = (label, connected) => {
    if (!status) return;
    status.lastChild.textContent = ` ${label}`;
    status.classList.toggle("connected", connected);
  };

  const relativeTime = (value) => {
    if (!value) return "Just now";
    const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
    if (seconds < 60) return "Just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr ago`;
    return new Date(value).toLocaleDateString(undefined, { day: "numeric", month: "short" });
  };

  const iconClass = (kind) => {
    if (kind === "online") return "fa-circle";
    if (kind === "offline") return "fa-arrow-right-from-bracket";
    if (kind === "member_joined") return "fa-user-check";
    if (kind === "quotation_added" || kind === "quotation_selected") return "fa-file-invoice-dollar";
    return "fa-list-check";
  };

  const addFeedItem = (activity, temporary = false) => {
    if (!feed) return;
    feed.querySelector(".activity-empty")?.remove();
    if (activity.id && feed.querySelector(`[data-activity-id="${activity.id}"]`)) return;
    const item = document.createElement("li");
    if (activity.id) item.dataset.activityId = activity.id;
    if (temporary) item.classList.add("presence-activity");
    const icon = document.createElement("span");
    icon.className = "activity-icon";
    icon.setAttribute("aria-hidden", "true");
    const symbol = document.createElement("i");
    symbol.className = `fa-solid ${iconClass(activity.kind)}`;
    icon.appendChild(symbol);
    const details = document.createElement("div");
    const message = document.createElement("strong");
    message.textContent = activity.message;
    const time = document.createElement("time");
    time.dateTime = activity.created_at || new Date().toISOString();
    time.textContent = relativeTime(activity.created_at);
    details.append(message, time);
    item.append(icon, details);
    feed.prepend(item);
    while (feed.children.length > 15) feed.lastElementChild.remove();
  };

  socket.on("connect", () => setStatus("Live", true));
  socket.on("disconnect", () => setStatus("Reconnecting…", false));
  socket.on("connect_error", () => setStatus("Updates unavailable", false));
  socket.on("activity:new", (activity) => addFeedItem(activity));
  socket.on("presence:event", (activity) => addFeedItem(activity, true));
  socket.on("presence:state", ({ users = [] }) => {
    if (!onlineTeam) return;
    onlineTeam.replaceChildren();
    if (!users.length) {
      const empty = document.createElement("span");
      empty.className = "muted";
      empty.textContent = "No team members online";
      onlineTeam.appendChild(empty);
      return;
    }
    users.forEach((user) => {
      const chip = document.createElement("span");
      chip.className = "online-person";
      const dot = document.createElement("i");
      dot.setAttribute("aria-hidden", "true");
      const label = document.createElement("span");
      label.textContent = `${user.name} · ${user.role}`;
      chip.append(dot, label);
      onlineTeam.appendChild(chip);
    });
  });
})();
