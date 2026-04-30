const fs = require('fs');
const path = require('path');

function copyDir(src, dest) {
  if (!fs.existsSync(src)) return;
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const from = path.join(src, entry.name);
    const to = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDir(from, to);
    } else {
      fs.copyFileSync(from, to);
    }
  }
}

fs.mkdirSync('dist', { recursive: true });
copyDir(path.join('src', 'renderer', 'styles'), path.join('dist', 'renderer', 'styles'));
fs.copyFileSync(path.join('src', 'renderer', 'index.html'), path.join('dist', 'renderer', 'index.html'));
copyDir('resources', path.join('dist', 'resources'));
