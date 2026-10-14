import * as THREE from 'three';
import {BUILDINGS, AMENITIES, TREE_POSITIONS} from './map-layout.js';
import {randomSeed} from './map-materials.js';

// All dimensions are illustrative plan units, not surveyed metres.
export function buildSite(scene, m, cameras) {
  const root = new THREE.Group(); scene.add(root);
  const targets = new Map(); const selectable = [];
  const boxGeometry = new THREE.BoxGeometry(1, 1, 1);
  function mesh(geometry, material, parent = root) {
    const obj = new THREE.Mesh(geometry, material); obj.castShadow = obj.receiveShadow = true; parent.add(obj); return obj;
  }
  function box(x, y, z, w, h, d, material, parent = root) {
    const obj = mesh(boxGeometry, material, parent); obj.position.set(x, y, z); obj.scale.set(w, h, d); return obj;
  }
  function cylinder(x, y, z, radius, height, material, parent = root) {
    const obj = mesh(new THREE.CylinderGeometry(radius, radius, height, 12), material, parent); obj.position.set(x, y, z); return obj;
  }
  function register(group, feature) {
    targets.set(feature.id, group); group.userData.feature = feature;
    group.traverse(obj => { if (obj.isMesh) { obj.userData.feature = feature; selectable.push(obj); } });
  }
  const ground = box(80, -.4, 55, 160, .8, 110, m.grass);
  ground.castShadow = false;
  box(80, -1.2, 55, 167, 1.5, 117, m.stone);

  // Continuous rounded perimeter and internal access roads, including the southern entrance.
  function road(points, width) {
    const curve = new THREE.CatmullRomCurve3(points.map(([x,z]) => new THREE.Vector3(x, .12, z)));
    const makeStrip = (w, y, material) => {
      const vertices = [], uvs = [], indices = [];
      for (let i = 0; i <= 200; i++) {
        const p = curve.getPoint(i / 200), t = curve.getTangent(i / 200);
        const normal = new THREE.Vector3(-t.z, 0, t.x).normalize().multiplyScalar(w / 2);
        vertices.push(p.x + normal.x, y, p.z + normal.z, p.x - normal.x, y, p.z - normal.z);
        uvs.push(0, i / 200, 1, i / 200);
        if (i < 200) { const k = i * 2; indices.push(k, k + 2, k + 1, k + 1, k + 2, k + 3); }
      }
      const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
      geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2)); geometry.setIndex(indices); geometry.computeVertexNormals();
      const strip = mesh(geometry, material); strip.castShadow = false;
    };
    makeStrip(width + 2.3, .12, m.paving); makeStrip(width, .15, m.asphalt);
  }
  road([[13,24],[13,14],[21,9],[80,9],[139,9],[147,16],[147,50],[147,86],[139,92],[100,92],[80,92],[24,92],[13,85],[13,24]], 8);
  road([[13,45],[31,43],[55,44],[69,48],[90,48],[105,44],[128,44],[147,45]], 8);
  road([[80,48],[80,70],[80,91],[80,110]], 15);
  for (let x = 25; x < 139; x += 10) {
    box(x, .17, 9, 3, .02, .13, m.white); box(x, .17, 92, 3, .02, .13, m.white);
  }

  function roof(group, w, d, height) {
    const a = [-w/2, height, -d/2], b = [w/2, height, -d/2], c = [w/2, height, d/2], e = [-w/2, height, d/2];
    const r1 = [-w*.27, height+3, 0], r2 = [w*.27, height+3, 0];
    const vertices = [...a,...r1,...b, ...b,...r1,...r2, ...e,...c,...r1, ...c,...r2,...r1, ...a,...e,...r1, ...b,...r2,...c];
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(vertices,3));
    const uv = []; for (let i=0; i<vertices.length; i+=3) uv.push(vertices[i]/w+.5, vertices[i+2]/d+.5);
    g.setAttribute('uv', new THREE.Float32BufferAttribute(uv,2)); g.computeVertexNormals(); mesh(g,m.roof,group);
    box(0,height+.02,0,w,.25,d,m.timber,group);
    box(0,height+3.03,0,w*.54,.12,.24,m.roof,group);
  }

  function windowPane(group,x,y,z,width,height,rotate=false) {
    const pane = new THREE.Group(); pane.position.set(x,y,z); pane.rotation.y = rotate ? Math.PI/2 : 0; group.add(pane);
    box(0,0,0,width+.24,height+.24,.2,m.trim,pane);
    box(0,0,.13,width,height,.08,m.glass,pane);
    box(0,0,.2,.06,height,.06,m.metal,pane);
    box(0,0,.2,width,.06,.06,m.metal,pane);
    box(0,-height/2-.16,.18,width+.45,.16,.5,m.stone,pane);
  }
  for (const feature of BUILDINGS) {
    const group = new THREE.Group(); group.position.set(feature.x,0,feature.z); root.add(group);
    const w = feature.w*.81, d = feature.d*.76, h = feature.id==='clubhouse' ? 6.3 : feature.id==='guardhouse' ? 3.6 : 4.7;
    box(0,.25,0,w+1.4,.5,d+1.4,m.stone,group);
    box(0,h/2+.5,0,w,h,d,m.plaster,group);
    box(0,.8,0,w+.05,.6,d+.05,m.stone,group);
    roof(group,w+1.6,d+1.8,h+.55);
    for (const x of [-w*.32,w*.32]) {
      windowPane(group,x,2.7,d/2+.02,2.8,2.3);
      const back = new THREE.Group(); back.rotation.y=Math.PI; group.add(back); windowPane(back,x,2.7,d/2+.02,2.8,2.3);
    }
    for (const z of [-d*.26,d*.26]) {
      windowPane(group,w/2+.02,2.7,z,2.3,2.1,true);
      const left = new THREE.Group(); left.rotation.y=Math.PI; group.add(left); windowPane(left,w/2+.02,2.7,z,2.3,2.1,true);
    }
    box(0,1.95,d/2+.07,1.8,2.9,.2,m.timber,group);
    box(.6,1.7,d/2+.23,.08,.5,.09,m.metal,group);
    box(0,.35,d/2+1.5,5,.5,3,m.paving,group);
    box(0,.17,d/2+3.15,5.8,.24,.7,m.stone,group);
    box(0,3.85,d/2+1.2,5.4,.2,3.2,m.timber,group);
    for (const x of [-2.35,2.35]) box(x,2,d/2+2.35,.19,3.7,.19,m.trim,group);
    if (feature.id.startsWith('house')) {
      const side = feature.x<80 ? 1 : -1;
      box(side*(w/2+2.7),.12,1,4.2,.18,d+2,m.paving,group);
      // A parked car provides familiar scale, without representing live traffic.
      const car = new THREE.Group(); car.position.set(side*(w/2+2.7),0,0); group.add(car);
      box(0,.7,0,2.1,.65,4.5,m.white,car); box(0,1.18,-.2,1.8,.62,2.5,m.glass,car);
      box(0,1.54,-.25,1.8,.12,1.8,m.white,car);
      for (const x of [-1.03,1.03]) for (const z of [-1.4,1.4]) {
        const wheel = cylinder(x,.45,z,.4,.22,m.metal,car); wheel.rotation.z=Math.PI/2;
      }
    }
    register(group, feature);
  }

  const poolFeature = AMENITIES[0], pool = new THREE.Group(); root.add(pool);
  pool.position.set(poolFeature.x,0,poolFeature.z);
  box(0,.16,0,41,.3,23,m.timber,pool);
  box(-.9,.35,0,33,.4,16.5,m.trim,pool);
  box(-.9,.57,0,31,.06,14.5,m.water,pool);
  // Fine pool tile grid is visible through the tinted surface.
  for (let x=-15; x<14; x+=2) box(x,.61,0,.025,.008,14,m.white,pool);
  for (let z=-6; z<=6; z+=2) box(-.9,.61,z,30,.008,.025,m.white,pool);
  for (const z of [-7,0,7]) {
    box(18,.55,z,1.8,.45,3.5,m.white,pool);
    const back=box(18,1,z-1.1,1.8,.15,1.5,m.white,pool); back.rotation.x=.5;
    cylinder(20,1.9,z,.055,3.8,m.metal,pool);
    const umbrella = mesh(new THREE.ConeGeometry(2.1,.8,32),m.white,pool); umbrella.position.set(20,3.8,z);
  }
  register(pool,poolFeature);

  const gardenFeature = AMENITIES[1], garden=new THREE.Group(); garden.position.set(31,0,24); root.add(garden);
  const path=mesh(new THREE.RingGeometry(9.7,12.7,96),m.paving,garden); path.rotation.x=-Math.PI/2; path.position.y=.18;
  for (let i=0; i<4; i++) {
    const angle=i*Math.PI/2+Math.PI/4, bench=new THREE.Group(); garden.add(bench);
    bench.position.set(Math.cos(angle)*10.7,0,Math.sin(angle)*10.7); bench.rotation.y=-angle+Math.PI/2;
    for(let slat=0;slat<4;slat++) box(0,.8,slat*.22-.33,3.5,.13,.17,m.timber,bench);
    box(0,1.3,-.55,3.5,.65,.12,m.timber,bench);
    for(const x of [-1.2,1.2]) box(x,.4,0,.15,.8,.75,m.metal,bench);
  }
  // Lawn picking surface makes the entire garden selectable.
  const lawn=mesh(new THREE.CircleGeometry(9.7,64),m.grass,garden); lawn.rotation.x=-Math.PI/2; lawn.position.y=.12;
  register(garden,gardenFeature);

  const rng=randomSeed(582);
  const trees=[...TREE_POSITIONS.filter(([x,z])=>z>15&&z<88&&x>18&&x<142),[31,24,1.2]];
  for(let x=5;x<=155;x+=6) { trees.push([x,3,.8+rng()*.4]); if(x<70||x>90)trees.push([x,107,.8+rng()*.4]); }
  for(let z=15;z<=96;z+=7) { trees.push([4,z,.9+rng()*.3],[156,z,.8+rng()*.4]); }
  const leafCanvas=document.createElement('canvas');leafCanvas.width=leafCanvas.height=64;
  const leafCtx=leafCanvas.getContext('2d');
  for(const [x,y,angle] of [[20,18,-.7],[40,20,.6],[18,40,-.8],[42,42,.7],[32,8,0]]){
    leafCtx.save();leafCtx.translate(x,y);leafCtx.rotate(angle);
    const gradient=leafCtx.createLinearGradient(-8,0,8,0);gradient.addColorStop(0,'#768954');gradient.addColorStop(.5,'#abb380');gradient.addColorStop(1,'#4e643e');
    leafCtx.fillStyle=gradient;leafCtx.beginPath();leafCtx.moveTo(0,-14);leafCtx.bezierCurveTo(15,-4,10,7,0,13);leafCtx.bezierCurveTo(-10,5,-12,-4,0,-14);leafCtx.fill();
    leafCtx.strokeStyle='#c0c396';leafCtx.lineWidth=.7;leafCtx.beginPath();leafCtx.moveTo(0,-12);leafCtx.lineTo(0,12);leafCtx.stroke();leafCtx.restore();
  }
  const leafTexture=new THREE.CanvasTexture(leafCanvas);leafTexture.colorSpace=THREE.SRGBColorSpace;
  const leafGeometry=new THREE.PlaneGeometry(1,1);
  const leafMaterial=new THREE.MeshStandardMaterial({map:leafTexture,alphaTest:.45,side:THREE.DoubleSide,roughness:1});
  const leafCount=850;
  const leaves=new THREE.InstancedMesh(leafGeometry,leafMaterial,trees.length*leafCount);
  leaves.castShadow=leaves.receiveShadow=true; root.add(leaves);
  const dummy=new THREE.Object3D(); let leafIndex=0;
  for(const [x,z,s] of trees) {
    cylinder(x,2.2*s,z,.17*s,4.4*s,m.bark);
    for(let b=0;b<4;b++) {
      const branch=cylinder(x+Math.cos(b*1.6)*.6*s,3.3*s,z+Math.sin(b*1.6)*.6*s,.07*s,2*s,m.bark);
      branch.rotation.z=Math.cos(b*1.6)*.65; branch.rotation.x=Math.sin(b*1.6)*.65;
    }
    for(let j=0;j<leafCount;j++) {
      const theta=rng()*Math.PI*2, vertical=rng()*2-1, radius=Math.cbrt(rng())*2.3*s;
      const spread=Math.sqrt(1-vertical*vertical);
      dummy.position.set(x+Math.cos(theta)*radius*spread,5.3*s+vertical*radius*.85,z+Math.sin(theta)*radius*spread);
      dummy.scale.setScalar((.5+rng()*.6)*s); dummy.rotation.set(rng()*6,rng()*6,rng()*6); dummy.updateMatrix();
      leaves.setMatrixAt(leafIndex,dummy.matrix); leaves.setColorAt(leafIndex,new THREE.Color().setHSL(.2+rng()*.035,.1,.48+rng()*.3)); leafIndex++;
    }
  }
  // Low clipped hedges along the residential plots.
  const hedgeMat=new THREE.MeshStandardMaterial({color:'#495b32',roughness:1});
  for(const x of [42,119]) for(const z of [61,78]) {
    box(x, .65, z-7, 20,1.1,.75,hedgeMat);
    box(x-10,.65,z, .75,1.1,14,hedgeMat);
  }
  for(const x of [22,61,99,138]) for(const z of [40,89]) {
    cylinder(x,2.6,z,.08,5.2,m.metal);
    box(x,5.25,z,.9,.16,.55,m.white);
  }
  for(const x of [72.5,87.5]) {
    box(x,.9,97,.55,1.8,.6,m.metal);
    box(x+(x<80?-2:2),1.6,97,4,.16,.18,m.white);
    for(let i=0;i<4;i++) box(x+(x<80?-i:i),1.6,97,.45,.18,.2,m.red);
  }
  const cameraGroup=new THREE.Group(); root.add(cameraGroup);
  cameras.forEach(feature=>{
    const group=new THREE.Group(); group.position.set(feature.x,0,feature.z); cameraGroup.add(group);
    cylinder(0,2.6,0,.08,5.2,m.metal,group); box(0,5.3,0,.7,.4,1.1,m.white,group); box(0,5.3,.57,.45,.25,.05,m.glass,group);
    register(group,feature);
    const fan=new THREE.Shape(); fan.moveTo(0,0);
    for(let i=0;i<=20;i++){const a=feature.angle-.4+i*.04;fan.lineTo(Math.cos(a)*15,-Math.sin(a)*15);} fan.closePath();
    const coverage=mesh(new THREE.ShapeGeometry(fan),new THREE.MeshBasicMaterial({color:'#37ad94',transparent:true,opacity:.10,depthWrite:false}),group);
    coverage.rotation.x=-Math.PI/2;coverage.position.y=.21;coverage.castShadow=false;
  });
  return {root,targets,selectable,cameraGroup};
}
