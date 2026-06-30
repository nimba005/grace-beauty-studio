
function fillFields(prefix, data) {
  Object.entries(data).forEach(([key, value]) => {
    const field = document.querySelector(`[data-edit-field="${prefix}-${key}"]`);
    if (!field) return;
    if (field.type === "checkbox") field.checked = Boolean(value);
    else field.value = value ?? "";
  });
  window.location.hash = prefix === "service" ? "services" : "products";
}
const siteHeader = document.querySelector(".site-header");
function syncHeaderHeight() {
  if (!siteHeader) return;
  document.documentElement.style.setProperty("--site-header-height", `${siteHeader.offsetHeight}px`);
  document.body.style.setProperty("--site-header-height", `${siteHeader.offsetHeight}px`);
}
if (siteHeader) {
  syncHeaderHeight();
  window.addEventListener("resize", syncHeaderHeight);
  window.addEventListener("load", syncHeaderHeight);
}
document.addEventListener("click", (event) => {
  const serviceButton = event.target.closest("[data-edit-service]");
  if (serviceButton) {
    const item = JSON.parse(serviceButton.dataset.editService);
    fillFields("service", {id:item.id,title:item.title,category:item.category,price:item.price,duration:item.duration,image:item.image_url,sort:item.sort_order,description:item.description,featured:item.is_featured,active:item.is_active});
  }
  const productButton = event.target.closest("[data-edit-product]");
  if (productButton) {
    const item = JSON.parse(productButton.dataset.editProduct);
    fillFields("product", {id:item.id,name:item.name,category:item.category,price:item.price,size:item.size,stock:item.stock_status,image:item.image_url,sort:item.sort_order,description:item.description,featured:item.is_featured,active:item.is_active});
  }
});
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});
const reviewType = document.querySelector("[data-review-type]");
const reviewItem = document.querySelector("[data-review-item]");
function syncReviewItems() {
  if (!reviewType || !reviewItem) return;
  const type = reviewType.value;
  let firstVisible = "";
  reviewItem.querySelectorAll("option").forEach((option) => {
    const matches = option.dataset.type === type;
    option.hidden = !matches;
    option.disabled = !matches;
    if (matches && !firstVisible) firstVisible = option.value;
  });
  if (!reviewItem.selectedOptions[0] || reviewItem.selectedOptions[0].disabled) {
    reviewItem.value = firstVisible;
  }
}
if (reviewType && reviewItem) {
  reviewType.addEventListener("change", syncReviewItems);
  syncReviewItems();
}
document.querySelectorAll("[data-service-browser]").forEach((browser) => {
  const tabs = browser.querySelectorAll("[data-service-tab]");
  const panels = browser.querySelectorAll("[data-service-panel]");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.serviceTab;
      tabs.forEach((item) => {
        const active = item === tab;
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
      });
      panels.forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.servicePanel === target);
      });
    });
  });
});
const navLinks = Array.from(document.querySelectorAll("[data-nav-section]"));
const observedSections = navLinks
  .map((link) => document.getElementById(link.dataset.navSection))
  .filter(Boolean);
function setActiveNav(sectionId) {
  navLinks.forEach((link) => {
    const active = link.dataset.navSection === sectionId;
    link.classList.toggle("is-active", active);
    if (active) link.setAttribute("aria-current", "true");
    else link.removeAttribute("aria-current");
  });
}
if (navLinks.length && observedSections.length) {
  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (visible) setActiveNav(visible.target.id);
    },
    { rootMargin: "-35% 0px -48% 0px", threshold: [0.08, 0.18, 0.32, 0.5] }
  );
  observedSections.forEach((section) => observer.observe(section));
  window.addEventListener("hashchange", () => {
    const sectionId = window.location.hash.replace("#", "");
    if (sectionId) setActiveNav(sectionId);
  });
}
const CART_KEY = "graceBeautyCart";
const INTERACTION_KEY = "graceBeautyInteracted";
const cartDrawer = document.querySelector("[data-cart-drawer]");
const cartItemsEl = document.querySelector("[data-cart-items]");
const cartEmptyEl = document.querySelector("[data-cart-empty]");
const cartStatusEl = document.querySelector("[data-cart-status]");
const cartCountEls = document.querySelectorAll("[data-cart-count]");
const bookingForm = document.querySelector("[data-booking-form]");
const authDrawer = document.querySelector("[data-auth-drawer]");
const authStatusEl = document.querySelector("[data-auth-status]");
const itemDetailModal = document.querySelector("[data-item-detail-modal]");
let detailItem = null;
let customerCartSyncTimer;
function customerSignedIn() {
  return document.body?.dataset.customerAuth === "signed-in";
}
function readCart() {
  try {
    const cart = JSON.parse(localStorage.getItem(CART_KEY) || "[]");
    return Array.isArray(cart) ? cart.map(normalizeCartItem).filter(Boolean) : [];
  }
  catch { return []; }
}
function normalizeCartItem(item) {
  if (!item || !item.type || !item.id) return null;
  return {
    type: item.type,
    id: String(item.id),
    name: item.name || "Selected item",
    meta: item.meta || "",
    price: item.price || "",
    quantity: Math.max(1, Number(item.quantity || 1)),
  };
}
function writeCart(cart) {
  localStorage.setItem(CART_KEY, JSON.stringify((cart || []).map(normalizeCartItem).filter(Boolean)));
  syncCustomerCart();
}
function syncCustomerCart() {
  if (!customerSignedIn()) return;
  clearTimeout(customerCartSyncTimer);
  customerCartSyncTimer = setTimeout(() => {
    fetch("/customer/cart", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({cart: readCart()}),
    }).catch(() => {});
  }, 300);
}
function mergeCart(savedCart) {
  const current = readCart();
  const merged = Array.isArray(savedCart) ? savedCart.slice() : [];
  const keys = new Set(merged.map(cartKey));
  current.forEach((item) => {
    const key = cartKey(item);
    if (!keys.has(key)) {
      merged.push(item);
      keys.add(key);
    }
  });
  localStorage.setItem(CART_KEY, JSON.stringify(merged));
}
function cartKey(item) {
  return `${item.type}:${item.id}`;
}
function markInteraction() {
  localStorage.setItem(INTERACTION_KEY, "true");
  syncGatedForms();
}
function hasInteraction() {
  return localStorage.getItem(INTERACTION_KEY) === "true";
}
function cartSummary(cart) {
  return cart.map((item) => `- ${item.type === "service" ? "Session" : "Product"}: ${item.name} x${item.quantity || 1} (${[item.meta, item.price].filter(Boolean).join(" - ") || "details on request"})`).join("\n");
}
function catalogItems() {
  return Array.from(document.querySelectorAll("[data-cart-add]")).map((button) => ({
    type: button.dataset.itemType,
    id: button.dataset.itemId,
    name: button.dataset.itemName,
    meta: button.dataset.itemMeta,
    price: button.dataset.itemPrice,
    quantity: 1,
  }));
}
function addItemToCart(item, quantity = 1) {
  const cart = readCart();
  const key = cartKey(item);
  const existing = cart.find((entry) => cartKey(entry) === key);
  if (existing) {
    existing.quantity = Math.max(1, Number(existing.quantity || 1)) + Math.max(1, Number(quantity || 1));
  } else {
    cart.push({...item, quantity: Math.max(1, Number(quantity || item.quantity || 1))});
  }
  writeCart(cart);
  renderCart();
  return existing ? existing.quantity : quantity;
}
function setItemQuantity(item, quantity) {
  const cart = readCart();
  const key = cartKey(item);
  const nextQuantity = Math.max(1, Number(quantity || 1));
  const updated = cart.map((entry) => cartKey(entry) === key ? {...entry, quantity: nextQuantity} : entry);
  writeCart(updated);
  renderCart();
}
function removeItemFromCart(item) {
  writeCart(readCart().filter((entry) => cartKey(entry) !== cartKey(item)));
  renderCart();
}
function findRequestedCatalogItem(message) {
  if (!/\b(add|cart|order|book|reserve|choose|get)\b/i.test(message)) return null;
  const text = message.toLowerCase();
  return catalogItems()
    .sort((a, b) => b.name.length - a.name.length)
    .find((item) => {
      const name = item.name.toLowerCase();
      const words = name.split(/\W+/).filter((word) => word.length > 2);
      return text.includes(name) || words.every((word) => text.includes(word));
    });
}
function renderCart() {
  const cart = readCart();
  document.querySelectorAll("[data-cart-add]").forEach((button) => {
    button.classList.remove("is-added");
    button.textContent = button.dataset.itemType === "service" ? "Book session" : "Add to cart";
  });
  const totalQuantity = cart.reduce((total, item) => total + Math.max(1, Number(item.quantity || 1)), 0);
  cartCountEls.forEach((el) => { el.textContent = totalQuantity; });
  if (!cartItemsEl || !cartEmptyEl) return;
  cartItemsEl.innerHTML = "";
  cartEmptyEl.hidden = cart.length > 0;
  cart.forEach((item) => {
    const row = document.createElement("article");
    row.className = "cart-item";
    row.innerHTML = `<div><strong></strong><span></span><small></small></div><div class="cart-qty"><button type="button" data-qty-dec aria-label="Decrease quantity">-</button><input type="number" min="1" max="20"><button type="button" data-qty-inc aria-label="Increase quantity">+</button></div><button type="button" data-cart-remove>Remove</button>`;
    row.querySelector("strong").textContent = item.name;
    row.querySelector("span").textContent = item.type === "service" ? "Session booking" : "Product order";
    row.querySelector("small").textContent = [item.meta, item.price].filter(Boolean).join(" - ");
    const quantityInput = row.querySelector("input");
    quantityInput.value = Math.max(1, Number(item.quantity || 1));
    row.querySelector("[data-qty-dec]").addEventListener("click", () => {
      setItemQuantity(item, Math.max(1, Number(quantityInput.value || 1) - 1));
    });
    row.querySelector("[data-qty-inc]").addEventListener("click", () => {
      setItemQuantity(item, Number(quantityInput.value || 1) + 1);
    });
    quantityInput.addEventListener("change", () => {
      setItemQuantity(item, quantityInput.value);
    });
    row.querySelector("[data-cart-remove]").addEventListener("click", () => {
      removeItemFromCart(item);
    });
    cartItemsEl.appendChild(row);
  });
}
function openItemDetail(item) {
  if (!itemDetailModal) return;
  detailItem = item;
  itemDetailModal.querySelector("[data-detail-image]").src = item.image || "";
  itemDetailModal.querySelector("[data-detail-image]").alt = item.name || "";
  itemDetailModal.querySelector("[data-detail-category]").textContent = item.category || item.type || "";
  itemDetailModal.querySelector("[data-detail-name]").textContent = item.name || "";
  itemDetailModal.querySelector("[data-detail-description]").textContent = item.description || "";
  itemDetailModal.querySelector("[data-detail-price]").textContent = item.price || "";
  itemDetailModal.querySelector("[data-detail-meta]").textContent = item.meta || "";
  itemDetailModal.querySelector("[data-detail-qty]").value = 1;
  itemDetailModal.setAttribute("aria-hidden", "false");
}
function closeItemDetail() {
  itemDetailModal?.setAttribute("aria-hidden", "true");
}
function syncGatedForms() {
  document.querySelectorAll("[data-gated-open]").forEach((button) => {
    button.hidden = !hasInteraction();
  });
  document.querySelectorAll("[data-gated-form]").forEach((form) => {
    if (!hasInteraction()) form.hidden = true;
  });
}
document.addEventListener("click", (event) => {
  const addButton = event.target.closest("[data-cart-add]");
  if (addButton) {
    const item = {
      type: addButton.dataset.itemType,
      id: addButton.dataset.itemId,
      name: addButton.dataset.itemName,
      meta: addButton.dataset.itemMeta,
      price: addButton.dataset.itemPrice,
      quantity: 1,
    };
    addItemToCart(item, 1);
    if (cartStatusEl) cartStatusEl.textContent = `${item.name} added to cart.`;
  }
  const detailButton = event.target.closest("[data-item-detail]");
  if (detailButton) {
    openItemDetail({
      type: detailButton.dataset.itemType,
      id: detailButton.dataset.itemId,
      name: detailButton.dataset.itemName,
      category: detailButton.dataset.itemCategory,
      meta: detailButton.dataset.itemMeta,
      price: detailButton.dataset.itemPrice,
      image: detailButton.dataset.itemImage,
      description: detailButton.dataset.itemDescription,
    });
  }
  if (event.target.closest("[data-item-detail-close]") || event.target === itemDetailModal) {
    closeItemDetail();
  }
  if (event.target.closest("[data-detail-add]") && detailItem) {
    const quantity = Number(itemDetailModal?.querySelector("[data-detail-qty]")?.value || 1);
    addItemToCart(detailItem, quantity);
    closeItemDetail();
    cartDrawer?.setAttribute("aria-hidden", "false");
  }
  if (event.target.closest("[data-cart-open]")) {
    cartDrawer?.setAttribute("aria-hidden", "false");
  }
  if (event.target.closest("[data-cart-close]")) {
    cartDrawer?.setAttribute("aria-hidden", "true");
  }
  if (event.target.closest("[data-auth-open]")) {
    authDrawer?.setAttribute("aria-hidden", "false");
  }
  if (event.target.closest("[data-auth-close]")) {
    authDrawer?.setAttribute("aria-hidden", "true");
  }
  const authTab = event.target.closest("[data-auth-tab]");
  if (authTab) {
    document.querySelectorAll("[data-auth-tab]").forEach((button) => {
      button.classList.toggle("active", button === authTab);
    });
    document.querySelectorAll("[data-auth-form]").forEach((form) => {
      form.classList.toggle("active", form.dataset.authForm === authTab.dataset.authTab);
    });
  }
  if (event.target.closest("[data-auth-logout]")) {
    fetch("/customer/logout", {method: "POST"})
      .then(() => {
        document.body.dataset.customerAuth = "guest";
        window.location.reload();
      })
      .catch(() => {});
  }
  const toggle = event.target.closest("[data-book-toggle]");
  if (toggle) {
    const panel = document.querySelector("[data-book-panel]");
    if (panel) panel.hidden = !panel.hidden;
  }
  if (event.target.closest("[data-book-close]")) {
    const panel = document.querySelector("[data-book-panel]");
    if (panel) panel.hidden = true;
  }
  const gatedOpen = event.target.closest("[data-gated-open]");
  if (gatedOpen) {
    const form = document.querySelector(`[data-gated-form="${gatedOpen.dataset.gatedOpen}"]`);
    if (form) {
      form.hidden = !form.hidden;
      if (!form.hidden) form.scrollIntoView({behavior: "smooth", block: "center"});
    }
  }
});
if (bookingForm) {
  bookingForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const cart = readCart();
    if (!cart.length) {
      cartStatusEl.textContent = "Add at least one product or service before checkout.";
      return;
    }
    const formData = new FormData(bookingForm);
    const payload = Object.fromEntries(formData.entries());
    payload.interest = cart.some((item) => item.type === "product") ? "Product order and booking" : "Salon booking";
    payload.cart_summary = cartSummary(cart);
    payload.cart = cart;
    cartStatusEl.textContent = "Sending booking...";
    try {
      const response = await fetch("/inquire", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "Could not submit booking.");
      cartStatusEl.textContent = result.message;
      bookingForm.reset();
      writeCart([]);
      markInteraction();
      renderCart();
    } catch (error) {
      cartStatusEl.textContent = error.message || "Could not submit booking. Please try WhatsApp or call.";
    }
  });
}
document.querySelectorAll("[data-auth-form='signup'],[data-auth-form='login']").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const mode = form.dataset.authForm;
    const payload = Object.fromEntries(new FormData(form).entries());
    payload.cart = readCart();
    if (authStatusEl) authStatusEl.textContent = mode === "signup" ? "Creating your account..." : "Signing you in...";
    try {
      const response = await fetch(`/customer/${mode}`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "Account request failed.");
      if (Array.isArray(result.cart)) localStorage.setItem(CART_KEY, JSON.stringify(result.cart));
      if (authStatusEl) authStatusEl.textContent = result.message || "Account updated.";
      window.location.reload();
    } catch (error) {
      if (authStatusEl) authStatusEl.textContent = error.message || "Please try again.";
    }
  });
});
if (customerSignedIn()) {
  fetch("/customer/cart")
    .then((response) => response.ok ? response.json() : null)
    .then((result) => {
      if (!result?.ok) return;
      mergeCart(result.cart);
      renderCart();
      syncCustomerCart();
    })
    .catch(() => {});
}
const assistantForm = document.querySelector("[data-assistant-form]");
const assistantMessages = document.querySelector("[data-assistant-messages]");
if (assistantForm && assistantMessages) {
  assistantForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = assistantForm.elements.message;
    const message = input.value.trim();
    if (!message) return;
    const userLine = document.createElement("p");
    userLine.className = "from-user";
    userLine.textContent = message;
    assistantMessages.appendChild(userLine);
    input.value = "";
    const replyLine = document.createElement("p");
    replyLine.textContent = "Thinking...";
    assistantMessages.appendChild(replyLine);
    const requestedItem = findRequestedCatalogItem(message);
    if (requestedItem) {
      const added = addItemToCart(requestedItem);
      replyLine.textContent = added
        ? `I added ${requestedItem.name} to your cart. Open the cart when you are ready to submit the booking or order.`
        : `${requestedItem.name} is already in your cart. Open the cart when you are ready to submit.`;
      assistantMessages.scrollTop = assistantMessages.scrollHeight;
      return;
    }
    try {
      const response = await fetch("/assistant/chat", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({message, cart: readCart()}),
      });
      const result = await response.json();
      replyLine.textContent = result.reply || "I can help you book. Add a product or service to the cart first.";
    } catch {
      replyLine.textContent = "I can help, but chat is not reachable right now. Open the cart to submit your booking.";
    }
    assistantMessages.scrollTop = assistantMessages.scrollHeight;
  });
}
renderCart();
syncGatedForms();
