
function fillFields(prefix, data) {
  Object.entries(data).forEach(([key, value]) => {
    const field = document.querySelector(`[data-edit-field="${prefix}-${key}"]`);
    if (!field) return;
    if (field.type === "checkbox") field.checked = Boolean(value);
    else field.value = value ?? "";
  });
  window.location.hash = prefix === "service" ? "services" : "products";
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
