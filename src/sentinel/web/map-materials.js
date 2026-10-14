import * as THREE from 'three';

export function randomSeed(seed = 173) {
  return () => { seed = (Math.imul(1664525, seed) + 1013904223) >>> 0; return seed / 4294967296; };
}

// Deterministic, locally generated surfaces. No external texture or image rights required.
export function createMaterials(renderer) {
  const textures = [];
  function surface(kind, color, roughness, repeat = 1) {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 512;
    const ctx = canvas.getContext('2d'); const rng = randomSeed(718);
    ctx.fillStyle = color; ctx.fillRect(0, 0, 512, 512);
    const pixels = ctx.getImageData(0, 0, 512, 512);
    for (let i = 0; i < pixels.data.length; i += 4) {
      const n = (rng() - .5) * (kind === 'grass' ? 48 : 26);
      for (let j = 0; j < 3; j++) pixels.data[i + j] += n;
    }
    ctx.putImageData(pixels, 0, 0);
    if (kind === 'grass') {
      for (let i = 0; i < 14000; i++) {
        ctx.strokeStyle = rng() > .5 ? 'rgba(180,177,106,.18)' : 'rgba(25,48,25,.19)';
        const x = rng() * 512, y = rng() * 512;
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + rng() * 3, y - 2 - rng() * 5); ctx.stroke();
      }
    }
    if (['tile', 'paving', 'wood'].includes(kind)) {
      const row = kind === 'tile' ? 24 : kind === 'wood' ? 32 : 64;
      for (let y = 0; y < 512; y += row) {
        ctx.fillStyle = 'rgba(24,24,20,.30)'; ctx.fillRect(0, y, 512, 2);
        ctx.fillStyle = 'rgba(255,255,240,.16)'; ctx.fillRect(0, y + 2, 512, 1);
        for (let x = -(y % (row * 2) ? row : 0); x < 512; x += row * 2) {
          ctx.fillStyle = 'rgba(20,24,20,.25)'; ctx.fillRect(x, y, 1, row);
        }
      }
    }
    const map = new THREE.CanvasTexture(canvas);
    map.colorSpace = THREE.SRGBColorSpace; map.wrapS = map.wrapT = THREE.RepeatWrapping;
    map.repeat.set(repeat, repeat); map.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
    textures.push(map);
    return new THREE.MeshStandardMaterial({map, bumpMap: map, bumpScale: kind === 'grass' ? .12 : .045, roughness});
  }
  const materials = {
    grass: surface('grass', '#657044', 1, 24), asphalt: surface('asphalt', '#46494a', .96, 12),
    paving: surface('paving', '#b9b3a6', .93, 3), plaster: surface('plaster', '#dfd9c8', .9, 2),
    roof: surface('tile', '#514c46', .86, 1), timber: surface('wood', '#88694b', .8, 2),
    stone: surface('paving', '#a19a8a', .95, 2),
    trim: new THREE.MeshStandardMaterial({color: '#ede8da', roughness: .65}),
    metal: new THREE.MeshStandardMaterial({color: '#343b3c', metalness: .7, roughness: .33}),
    glass: new THREE.MeshPhysicalMaterial({color: '#758b8c', metalness: .35, roughness: .12, clearcoat: 1, envMapIntensity: 1.4}),
    water: new THREE.MeshPhysicalMaterial({color: '#328791', metalness: .25, roughness: .13, clearcoat: 1, transparent: true, opacity: .85}),
    white: new THREE.MeshStandardMaterial({color: '#e5e0d3', roughness: .75}),
    red: new THREE.MeshStandardMaterial({color: '#993a2a', roughness: .7}),
    bark: surface('wood', '#63533c', 1),
  };
  return {materials, textures};
}
