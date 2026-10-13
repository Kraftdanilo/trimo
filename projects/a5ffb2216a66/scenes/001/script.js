// Génération des particules (100 en fond)
for (let i = 0; i < 100; i++) {
  const p = document.createElement('div');
  p.className = 'particle';
  p.style.left = `${Math.random() * 100}%`;
  p.style.top = `${Math.random() * 100}%`;
  p.style.animationDelay = `${Math.random() * 2.5}s`;
  p.style.animationDuration = `${2 + Math.random() * 3}s`;
  document.body.appendChild(p);
}