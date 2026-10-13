'use strict';
// Demo fields are never sent, stored, or read. The card scene has no submit control.
if (document.body.dataset.store === 'riverside-deals') {
  setTimeout(() => {
    const face = document.getElementById('late-face').content.cloneNode(true);
    face.querySelector('form').addEventListener('submit', event => event.preventDefault());
    document.body.append(face);
  },2000);
}
document.querySelectorAll('form').forEach(form => form.addEventListener('submit', event => event.preventDefault()));
