// File drop
const fileDrop = document.getElementById('fileDrop');
const fileInput = document.getElementById('fileInput');
const fileNameEl = document.getElementById('fileName');

if (fileDrop && fileInput) {
  fileDrop.addEventListener('click', () => fileInput.click());

  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) {
      fileNameEl.textContent = '✅ ' + fileInput.files[0].name;
    }
  });

  fileDrop.addEventListener('dragover', (e) => {
    e.preventDefault();
    fileDrop.classList.add('dragover');
  });

  fileDrop.addEventListener('dragleave', () => fileDrop.classList.remove('dragover'));

  fileDrop.addEventListener('drop', (e) => {
    e.preventDefault();
    fileDrop.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) {
      const dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
      fileNameEl.textContent = '✅ ' + file.name;
    }
  });
}

// Copy to clipboard
function copyText(text) {
  navigator.clipboard.writeText(text).then(() => {
    const btn = event.target.closest('button');
    const orig = btn.textContent;
    btn.textContent = '✅';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  });
}

// Auto-dismiss alerts
document.querySelectorAll('.alert').forEach(el => {
  setTimeout(() => {
    el.style.transition = 'opacity .5s';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 500);
  }, 4000);
});
