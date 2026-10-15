import * as THREE from 'three';
import {OrbitControls} from './vendor/OrbitControls.js';
import {BUILDINGS, AMENITIES} from './map-layout.js';
import {createMaterials} from './map-materials.js';
import {buildSite} from './map-scene.js?v=coordinates-1';

export function mount(canvas, {root, cameras, onSelect}) {
  let renderer;
  try { renderer = new THREE.WebGLRenderer({canvas, antialias: true, powerPreference: 'high-performance'}); }
  catch { throw new Error('The realistic map requires WebGL 2. Enable browser hardware acceleration and reload.'); }
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.75));
  renderer.shadowMap.enabled=true; renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  renderer.toneMapping=THREE.ACESFilmicToneMapping; renderer.toneMappingExposure=1.05;
  const scene=new THREE.Scene(); scene.background=new THREE.Color('#c9cfc9');
  const camera=new THREE.PerspectiveCamera(38,1,.5,1200);
  const controls=new OrbitControls(camera,canvas);
  controls.target.set(80,0,55); controls.minDistance=18; controls.maxDistance=520;
  controls.maxPolarAngle=Math.PI*.47; controls.minPolarAngle=.12;
  controls.enableDamping=false; controls.screenSpacePanning=true;
  const listeners=new AbortController();
  let dirty=true, disposed=false, selected=null;
  const invalidate=()=>{dirty=true;}; controls.addEventListener('change',invalidate);
  const sky=new THREE.HemisphereLight('#c9dcec','#75674c',2.0);scene.add(sky);
  const sun=new THREE.DirectionalLight('#fff1d5',3.1); sun.position.set(18,110,12);sun.target.position.set(80,0,55);
  scene.add(sun,sun.target);sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);
  Object.assign(sun.shadow.camera,{left:-110,right:110,top:90,bottom:-90,near:1,far:280});
  sun.shadow.normalBias=.14;sun.shadow.bias=-.00008;sun.shadow.radius=3;

  // A local sky environment gives glass and water a reflected sky/ground gradient.
  const skyCanvas=document.createElement('canvas');skyCanvas.width=512;skyCanvas.height=256;
  const ctx=skyCanvas.getContext('2d'), gradient=ctx.createLinearGradient(0,0,0,256);
  gradient.addColorStop(0,'#7fabc9');gradient.addColorStop(.45,'#dfe7e3');gradient.addColorStop(.52,'#c4c4ad');gradient.addColorStop(1,'#5c6550');
  ctx.fillStyle=gradient;ctx.fillRect(0,0,512,256);
  ctx.fillStyle='#fff5dd';ctx.beginPath();ctx.arc(90,65,14,0,Math.PI*2);ctx.fill();
  const skyTexture=new THREE.CanvasTexture(skyCanvas);skyTexture.mapping=THREE.EquirectangularReflectionMapping;skyTexture.colorSpace=THREE.SRGBColorSpace;
  const pmrem=new THREE.PMREMGenerator(renderer), environment=pmrem.fromEquirectangular(skyTexture);
  scene.environment=environment.texture;scene.environmentIntensity=.35;pmrem.dispose();skyTexture.dispose();
  const {materials,textures}=createMaterials(renderer);
  const cameraFeatures=cameras.filter(item=>item.map_position).map(item=>{
    const {x,y}=item.map_position;
    return {x:80+x,z:55-y,id:`camera-${item.id}`,label:item.name,type:'Camera',icon:'◉',state:'Placed camera',
      description:`${item.source_label}. Position configured in plan units; not a surveyed GPS location.`,
      facts:[['X',x],['Y',y],['Source',item.source_type]]};
  });
  const site=buildSite(scene,materials,cameraFeatures);
  const robotFeature={id:'patrol-robot',label:'Patrol robot · simulation',type:'Simulation',icon:'▣',state:'Simulated patrol',x:13,z:24,
    description:'Virtual patrol follows the perimeter road. No physical robot is connected or controlled.',facts:[['Route','Perimeter road'],['Mode','Simulation']]};
  const features=[...BUILDINGS,...AMENITIES,...cameraFeatures,robotFeature,
    {id:'origin',label:'(0, 0)',type:'Coordinates',icon:'+',state:'Plan origin',x:80,z:55,
      description:'Site center. Positive X is east/right; positive Y is north/up. Plan units are not surveyed metres.',facts:[['X',0],['Y',0]]}];
  const labelLayer=document.createElement('div');labelLayer.className='map-label-layer';canvas.after(labelLayer);
  const labelNodes=new Map();
  for(const feature of features){
    const label=document.createElement(feature.id==='origin'?'span':'button');label.type='button';label.className='map-place-label';label.textContent=feature.label;
    if(feature.id==='origin'){label.style.pointerEvents='none';label.style.marginLeft='32px';}
    if(feature.type==='Camera'){
      label.classList.add('map-camera-pin');label.title=feature.label;label.setAttribute('aria-label',feature.label);
      label.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10 5-3v10l-5-3"/></svg>';
    }
    label.addEventListener('click',()=>select(feature.id,true),{signal:listeners.signal});labelLayer.append(label);labelNodes.set(feature.id,label);
  }
  const selection=new THREE.Box3Helper(new THREE.Box3(),0x218775);selection.visible=false;scene.add(selection);
  function setAlerts(alerts){
    if(disposed)return;
    const groups=new Map();
    for(const alert of alerts){
      if(alert.status!=='pending'||!alert.map_position)continue;
      const {x,y}=alert.map_position,id=`alerts-${x}-${y}`;
      if(!groups.has(id))groups.set(id,{id,x:80+x,z:55-y,items:[]});
      groups.get(id).items.push(alert);
    }
    for(let i=features.length-1;i>=0;i--)if(features[i].type==='Alert'){
      labelNodes.get(features[i].id)?.remove();labelNodes.delete(features[i].id);features.splice(i,1);
    }
    for(const group of groups.values()){
      const feature={...group,type:'Alert',icon:'!',state:'Pending · review required',label:`${group.items.length} pending alert${group.items.length===1?'':'s'}`,
        description:group.items.map(item=>`${item.camera_name||'Uploaded media'}: ${item.description}`).join('\n'),
        facts:[['Pending',group.items.length],['X',group.x-80],['Y',55-group.z],['Location','At detection time']]};
      features.push(feature);
      const label=document.createElement('button');label.type='button';label.className='map-place-label map-alert-pin';
      label.textContent=`! ${group.items.length}`;label.setAttribute('aria-label',`${feature.label} at (${group.x-80}, ${55-group.z})`);
      // Removed nodes own their listener; avoid accumulating AbortSignal listeners on every refresh.
      label.addEventListener('click',()=>select(feature.id,true));labelLayer.append(label);labelNodes.set(feature.id,label);
    }
    if(selected?.type==='Alert'){
      const updated=features.find(item=>item.id===selected.id);
      if(updated){selected=updated;onSelect(updated);}
      else{selected=null;selection.visible=false;onSelect({type:'Alerts',icon:'✓',label:'Location cleared',state:'No pending alerts',description:'There are no longer pending alerts at this location.',facts:[]});}
    }
    invalidate();
  }
  function select(id,focus=false){
    const feature=features.find(item=>item.id===id);if(!feature)return;
    selected=feature;
    if(feature.type==='Camera'&&!site.cameraGroup.visible)toggleCameras(true);
    const group=site.targets.get(id);if(group)selection.box.setFromObject(group);selection.visible=Boolean(group)&&feature.type!=='Camera';
    if(focus){
      const offset=camera.position.clone().sub(controls.target).normalize().multiplyScalar(feature.type==='Camera'?36:65);
      controls.target.set(feature.x,2,feature.z);camera.position.copy(controls.target).add(offset);controls.update();
    }
    labelNodes.forEach((label,key)=>label.classList.toggle('selected',key===id));onSelect(feature);invalidate();
  }
  function reset(){
    selected=null;selection.visible=false;
    controls.target.set(80,0,60);
    const narrow=canvas.clientWidth<550;
    camera.position.set(80+(narrow?230:135),narrow?310:180,60+(narrow?285:163));
    controls.update();
    labelNodes.forEach(label=>label.classList.remove('selected'));
    onSelect({id:'overview',label:'Sentinel Residences',icon:'⌂',type:'Master plan',state:'Site overview',description:'Explore the residences, landscaped garden and shared amenities. Select a place for a closer architectural view.',facts:[['Homes','4'],['Amenities','3'],['Cameras',cameras.length]]});
    invalidate();
  }
  function zoom(factor){const offset=camera.position.clone().sub(controls.target);offset.setLength(THREE.MathUtils.clamp(offset.length()/factor,18,520));camera.position.copy(controls.target).add(offset);controls.update();invalidate();}
  function toggleCameras(visible){
    site.cameraGroup.visible=visible;
    const button=root.querySelector('[data-map-action="cameras"]');button.classList.toggle('active',visible);button.setAttribute('aria-pressed',String(visible));
    if(!visible&&selected?.type==='Camera')selection.visible=false;invalidate();
  }
  root.querySelectorAll('[data-map-feature]').forEach(button=>button.addEventListener('click',()=>select(button.dataset.mapFeature,true),{signal:listeners.signal}));
  root.querySelectorAll('[data-map-action]').forEach(button=>button.addEventListener('click',()=>{
    const action=button.dataset.mapAction;
    if(action==='zoom-in')zoom(1.2);if(action==='zoom-out')zoom(1/1.2);if(action==='reset')reset();if(action==='cameras')toggleCameras(!site.cameraGroup.visible);
  },{signal:listeners.signal}));
  const raycaster=new THREE.Raycaster();let down=null;
  canvas.addEventListener('pointerdown',event=>{down={x:event.clientX,y:event.clientY};},{signal:listeners.signal});
  canvas.addEventListener('pointerup',event=>{
    if(!down||Math.hypot(event.clientX-down.x,event.clientY-down.y)>5)return;
    down=null;const r=canvas.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((event.clientX-r.left)/r.width*2-1,-(event.clientY-r.top)/r.height*2+1),camera);
    const hit=raycaster.intersectObjects(site.selectable,false).find(hit=>hit.object.userData.feature.type!=='Camera'||site.cameraGroup.visible);
    if(hit)select(hit.object.userData.feature.id);
  },{signal:listeners.signal});
  canvas.addEventListener('pointercancel',()=>{down=null;},{signal:listeners.signal});
  canvas.addEventListener('keydown',event=>{
    if(event.key==='Home'){event.preventDefault();reset();}
    else if(['+','=','-'].includes(event.key)){event.preventDefault();zoom(event.key==='-'?1/1.15:1.15);}
    else if(event.key.startsWith('Arrow')){
      event.preventDefault();const offset=camera.position.clone().sub(controls.target), spherical=new THREE.Spherical().setFromVector3(offset);
      spherical.theta+=event.key==='ArrowLeft'?.1:event.key==='ArrowRight'?-.1:0;
      spherical.phi=THREE.MathUtils.clamp(spherical.phi+(event.key==='ArrowUp'?-.08:event.key==='ArrowDown'?.08:0),.12,Math.PI*.47);
      camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(spherical));controls.update();invalidate();
    }
  },{signal:listeners.signal});
  function resize(){const w=canvas.clientWidth,h=canvas.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();invalidate();}
  const observer=new ResizeObserver(resize);observer.observe(canvas);resize();reset();
  function dispose(){
    if(disposed)return;disposed=true;cancelAnimationFrame(frame);observer.disconnect();listeners.abort();controls.dispose();labelLayer.remove();
    const geometries=new Set(),mats=new Set();scene.traverse(obj=>{if(obj.geometry)geometries.add(obj.geometry);if(obj.material)(Array.isArray(obj.material)?obj.material:[obj.material]).forEach(mat=>mats.add(mat));});
    geometries.forEach(g=>g.dispose());mats.forEach(m=>{if(m.map&&!textures.includes(m.map))m.map.dispose();m.dispose();});textures.forEach(t=>t.dispose());environment.dispose();renderer.dispose();
  }
  let lastTime=0,patrolTime=0;
  function render(time){
    if(!canvas.isConnected){dispose();return;}
    const delta=lastTime?Math.min((time-lastTime)/1000,.1):0;lastTime=time;
    if(!document.hidden){
      patrolTime+=delta;site.updatePatrol(patrolTime);
      robotFeature.x=site.robot.position.x;robotFeature.z=site.robot.position.z;
      if(selected?.id==='patrol-robot')selection.box.setFromObject(site.robot);
      dirty=true;
    }
    if(dirty&&!document.hidden){
      dirty=false;renderer.render(scene,camera);
      const vector=new THREE.Vector3();
      features.forEach(feature=>{
        const label=labelNodes.get(feature.id);
        vector.set(feature.x,feature.type==='Camera'?.5:feature.type==='Residence'?9:feature.id==='clubhouse'?11:6,feature.z).project(camera);
        const visible=vector.z<1&&vector.z>-1&&Math.abs(vector.x)<.96&&Math.abs(vector.y)<.88&&(feature.type!=='Camera'||site.cameraGroup.visible);
        label.hidden=!visible;label.style.left=`${(vector.x*.5+.5)*100}%`;label.style.top=`${(-vector.y*.5+.5)*100}%`;
      });
    }
    frame=requestAnimationFrame(render);
  }
  let frame=requestAnimationFrame(render);
  window.addEventListener('pagehide',dispose,{once:true,signal:listeners.signal});
  return {dispose,select,reset,setAlerts};
}
