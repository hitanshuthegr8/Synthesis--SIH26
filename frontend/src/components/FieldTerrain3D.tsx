import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Rotate3d, RotateCcw, Scan } from "lucide-react";
import { extentOf, formatValue, indiaRings, insideIndia, normalise, normaliseLinear, type FieldStats, type Grid, type IndiaMask } from "./fieldGeometry";
import { paletteRgb, type FieldPalette } from "./fieldPalette";

type Cell = { row: number; column: number; value: number; latitude: number; longitude: number };
type Hover = Cell & { x: number; y: number; flip: boolean };
type View = "default" | "top";
type TerrainHandle = { setRelief: (relief: number) => void; setSpin: (spin: boolean) => void; fly: (view: View) => void; dispose: () => void };

const baseDepth = 0.7;
const surfaceLift = 0.12;
const defaultRelief = 5;
const views: Record<View, { position: THREE.Vector3; target: THREE.Vector3 }> = {
  default: { position: new THREE.Vector3(-5, 30, 36), target: new THREE.Vector3(0, 0, 1.5) },
  top: { position: new THREE.Vector3(0, 62, 0.01), target: new THREE.Vector3(0, 0, 0) },
};

export function FieldTerrain3D({ grid, stats, mask, palette, units, onCellSelect, onUnsupported }: {
  grid: Grid;
  stats: FieldStats;
  mask: IndiaMask;
  palette: FieldPalette;
  units: string;
  onCellSelect?: (value: number, latitude: number, longitude: number) => void;
  onUnsupported: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<TerrainHandle | null>(null);
  const [relief, setRelief] = useState(defaultRelief);
  const [spin, setSpin] = useState(false);
  const [hover, setHover] = useState<Hover | null>(null);
  const reliefRef = useRef(relief);
  const selectRef = useRef(onCellSelect);
  reliefRef.current = relief;
  selectRef.current = onCellSelect;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      onUnsupported();
      return;
    }
    const handle = createTerrainScene(container, renderer, { grid, stats, mask, palette, relief: reliefRef.current }, {
      onHover: setHover,
      onSelect: (cell) => selectRef.current?.(cell.value, cell.latitude, cell.longitude),
    });
    handleRef.current = handle;
    return () => {
      handle.dispose();
      handleRef.current = null;
      setHover(null);
    };
  }, [grid, stats, mask, palette]);

  useEffect(() => { handleRef.current?.setRelief(relief); }, [relief]);
  useEffect(() => { handleRef.current?.setSpin(spin); }, [spin, grid]);

  return <div className="terrain" ref={containerRef}>
    <div className="terrain-toolbar" onPointerDown={(event) => event.stopPropagation()}>
      <button onClick={() => handleRef.current?.fly("default")} title="Reset camera"><RotateCcw size={13} /> Reset</button>
      <button onClick={() => handleRef.current?.fly("top")} title="Look straight down"><Scan size={13} /> Top</button>
      <button className={spin ? "active" : ""} onClick={() => setSpin(!spin)} title="Auto-rotate"><Rotate3d size={13} /> Spin</button>
      <label className="terrain-relief" title="Vertical exaggeration">RELIEF<input type="range" min={0} max={14} step={0.5} value={relief} onChange={(event) => setRelief(Number(event.target.value))} /></label>
    </div>
    {hover && <div className={`terrain-tooltip${hover.flip ? " flip" : ""}`} style={{ left: hover.x, top: hover.y }}>
      <strong>{formatValue(hover.value, units)}</strong>
      <span>{hover.latitude.toFixed(2)}°N · {hover.longitude.toFixed(2)}°E</span>
    </div>}
    <div className="terrain-hint">Drag to orbit · Scroll to zoom · Right-drag to pan · Click a cell to inspect</div>
  </div>;
}

function createTerrainScene(
  container: HTMLDivElement,
  renderer: THREE.WebGLRenderer,
  { grid, stats, mask, palette, relief: initialRelief }: { grid: Grid; stats: FieldStats; mask: IndiaMask; palette: FieldPalette; relief: number },
  events: { onHover: (hover: Hover | null) => void; onSelect: (cell: Cell) => void },
): TerrainHandle {
  const { latitudes, longitudes, values } = grid;
  const rows = latitudes.length;
  const columns = longitudes.length;
  const extent = extentOf(grid);
  const centerLongitude = (extent.west + extent.east) / 2;
  const centerLatitude = (extent.south + extent.north) / 2;
  const longitudeCorrection = Math.cos((centerLatitude * Math.PI) / 180);
  const toX = (longitude: number) => (longitude - centerLongitude) * longitudeCorrection;
  const toZ = (latitude: number) => centerLatitude - latitude;
  const latitudeStep = (extent.north - extent.south) / (rows - 1);
  const longitudeStep = (extent.east - extent.west) / (columns - 1);
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let relief = initialRelief;
  let displayedRelief = reducedMotion ? relief : 0;
  const heightOf = (normalised: number, scale = displayedRelief) => surfaceLift + normalised * scale;
  const colorOf = (normalised: number) => new THREE.Color().setRGB(...paletteRgb(palette, normalised), THREE.SRGBColorSpace);

  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  container.prepend(renderer.domElement);

  // Render on demand: an idle terrain costs nothing, which matters on laptops without a discrete GPU.
  let dirty = true;
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x071418, 70, 150);
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 400);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 10;
  controls.maxDistance = 140;
  controls.maxPolarAngle = Math.PI * 0.47;
  controls.autoRotateSpeed = 0.7;

  scene.add(new THREE.HemisphereLight(0xe3f6ff, 0x0c1c21, 1.15));
  const sun = new THREE.DirectionalLight(0xffffff, 1.9);
  sun.position.set(-20, 32, 16);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -26, right: 26, top: 26, bottom: -26, near: 1, far: 90 });
  sun.shadow.bias = -0.0008;
  scene.add(sun);

  // Temperature surface: full-resolution grid, clipped to the coastline by the mask texture.
  const normalised = new Float32Array(rows * columns);
  const positions = new Float32Array(rows * columns * 3);
  const colors = new Float32Array(rows * columns * 3);
  const uvs = new Float32Array(rows * columns * 2);
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      const index = row * columns + column;
      const level = normaliseLinear(values[row][column], stats);
      const color = colorOf(normalise(values[row][column], stats));
      normalised[index] = level;
      positions.set([toX(longitudes[column]), heightOf(level), toZ(latitudes[row])], index * 3);
      colors.set([color.r, color.g, color.b], index * 3);
      uvs.set([column / (columns - 1), row / (rows - 1)], index * 2);
    }
  }
  const indices = new Uint32Array((rows - 1) * (columns - 1) * 6);
  let cursor = 0;
  for (let row = 0; row < rows - 1; row += 1) {
    for (let column = 0; column < columns - 1; column += 1) {
      const a = row * columns + column;
      const b = a + 1;
      const d = a + columns;
      indices.set([a, b, d, b, d + 1, d], cursor);
      cursor += 6;
    }
  }
  const surfaceGeometry = new THREE.BufferGeometry();
  surfaceGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  surfaceGeometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  surfaceGeometry.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));
  surfaceGeometry.setIndex(new THREE.BufferAttribute(indices, 1));
  const maskTexture = new THREE.CanvasTexture(mask.canvas);
  maskTexture.anisotropy = renderer.capabilities.getMaxAnisotropy();
  const surface = new THREE.Mesh(surfaceGeometry, new THREE.MeshStandardMaterial({
    vertexColors: true, alphaMap: maskTexture, alphaTest: 0.5, roughness: 0.55, metalness: 0.04, side: THREE.DoubleSide,
  }));
  surface.castShadow = true;
  surface.receiveShadow = true;
  scene.add(surface);

  // Coastline curtain walls and outlines, sampled bilinearly so they meet the surface edge.
  const sample = (longitude: number, latitude: number, source: ArrayLike<number> = normalised) => {
    const rowPosition = Math.max(0, Math.min(rows - 1, (latitude - extent.south) / latitudeStep));
    const columnPosition = Math.max(0, Math.min(columns - 1, (longitude - extent.west) / longitudeStep));
    const row = Math.min(rows - 2, Math.floor(rowPosition));
    const column = Math.min(columns - 2, Math.floor(columnPosition));
    const rowRatio = rowPosition - row;
    const columnRatio = columnPosition - column;
    const at = (r: number, c: number) => source[r * columns + c];
    return (at(row, column) * (1 - columnRatio) + at(row, column + 1) * columnRatio) * (1 - rowRatio)
      + (at(row + 1, column) * (1 - columnRatio) + at(row + 1, column + 1) * columnRatio) * rowRatio;
  };
  const wallPositions: number[] = [];
  const wallColors: number[] = [];
  const wallIndices: number[] = [];
  const wallLevels: number[] = [];
  const rimPositions: number[] = [];
  const rimLevels: number[] = [];
  const basePositions: number[] = [];
  const colorLevels = new Float32Array(rows * columns);
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) colorLevels[row * columns + column] = normalise(values[row][column], stats);
  }
  for (const ring of indiaRings) {
    const ringLongitudes = ring.map(([longitude]) => longitude);
    const ringLatitudes = ring.map(([, latitude]) => latitude);
    // Tiny islands get an outline only; full-height walls on them read as shards.
    const walled = (Math.max(...ringLongitudes) - Math.min(...ringLongitudes)) * (Math.max(...ringLatitudes) - Math.min(...ringLatitudes)) > 0.5;
    const start = wallPositions.length / 3;
    let previousLevel = 0;
    ring.forEach(([longitude, latitude], index) => {
      const level = sample(longitude, latitude);
      const x = toX(longitude);
      const z = toZ(latitude);
      if (walled) {
        const top = colorOf(sample(longitude, latitude, colorLevels));
        wallPositions.push(x, heightOf(level), z, x, -baseDepth, z);
        wallColors.push(top.r, top.g, top.b, top.r * 0.12, top.g * 0.14, top.b * 0.16);
        wallLevels.push(level);
      }
      if (index) {
        const previous = ring[index - 1];
        rimPositions.push(toX(previous[0]), 0, toZ(previous[1]), x, 0, z);
        rimLevels.push(previousLevel, level);
        basePositions.push(toX(previous[0]), -baseDepth, toZ(previous[1]), x, -baseDepth, z);
        const topIndex = start + index * 2;
        if (walled) wallIndices.push(topIndex - 2, topIndex - 1, topIndex, topIndex, topIndex - 1, topIndex + 1);
      }
      previousLevel = level;
    });
  }
  const wallGeometry = new THREE.BufferGeometry();
  wallGeometry.setAttribute("position", new THREE.Float32BufferAttribute(wallPositions, 3));
  wallGeometry.setAttribute("color", new THREE.Float32BufferAttribute(wallColors, 3));
  wallGeometry.setIndex(wallIndices);
  wallGeometry.computeVertexNormals();
  const walls = new THREE.Mesh(wallGeometry, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.7, metalness: 0.1, side: THREE.DoubleSide }));
  walls.castShadow = true;
  scene.add(walls);
  const rimGeometry = new THREE.BufferGeometry();
  rimGeometry.setAttribute("position", new THREE.Float32BufferAttribute(rimPositions, 3));
  scene.add(new THREE.LineSegments(rimGeometry, new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.55 })));
  const baseGeometry = new THREE.BufferGeometry();
  baseGeometry.setAttribute("position", new THREE.Float32BufferAttribute(basePositions, 3));
  scene.add(new THREE.LineSegments(baseGeometry, new THREE.LineBasicMaterial({ color: 0x5fd4bd, transparent: true, opacity: 0.8 })));

  const floor = new THREE.Mesh(new THREE.PlaneGeometry(260, 260), new THREE.MeshStandardMaterial({ color: 0x0a1b20, roughness: 0.95 }));
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -baseDepth - 0.01;
  floor.receiveShadow = true;
  scene.add(floor);
  const gridLines = new THREE.GridHelper(140, 56, 0x2c5a5f, 0x16343a);
  gridLines.position.y = -baseDepth;
  (gridLines.material as THREE.Material).transparent = true;
  (gridLines.material as THREE.Material).opacity = 0.45;
  scene.add(gridLines);

  const makeMarker = (color: number, radius: number) => {
    const group = new THREE.Group();
    const material = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.9, depthTest: false });
    const pillar = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, 1, 12), material);
    const head = new THREE.Mesh(new THREE.SphereGeometry(radius * 3.2, 20, 14), material);
    const halo = new THREE.Mesh(new THREE.RingGeometry(radius * 5, radius * 7, 40), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.55, side: THREE.DoubleSide, depthTest: false }));
    halo.rotation.x = -Math.PI / 2;
    group.add(pillar, head, halo);
    group.renderOrder = 10;
    group.children.forEach((child) => { child.renderOrder = 10; });
    group.visible = false;
    scene.add(group);
    return { group, pillar, head, halo, cell: null as Cell | null };
  };
  const hoverMarker = makeMarker(0xffffff, 0.035);
  const selectedMarker = makeMarker(0xffd166, 0.06);
  const placeMarker = (marker: ReturnType<typeof makeMarker>, cell: Cell | null) => {
    marker.cell = cell;
    marker.group.visible = Boolean(cell);
    dirty = true;
    if (!cell) return;
    const top = heightOf(normalised[cell.row * columns + cell.column]);
    marker.group.position.set(toX(cell.longitude), 0, toZ(cell.latitude));
    marker.pillar.scale.y = top + baseDepth;
    marker.pillar.position.y = (top - baseDepth) / 2;
    marker.head.position.y = top + 0.15;
    marker.halo.position.y = top + 0.02;
  };

  const applyRelief = (scale: number) => {
    for (let index = 0; index < normalised.length; index += 1) positions[index * 3 + 1] = heightOf(normalised[index], scale);
    surfaceGeometry.attributes.position.needsUpdate = true;
    surfaceGeometry.computeVertexNormals();
    const wallPosition = wallGeometry.attributes.position as THREE.BufferAttribute;
    wallLevels.forEach((level, index) => wallPosition.setY(index * 2, heightOf(level, scale)));
    wallPosition.needsUpdate = true;
    wallGeometry.computeVertexNormals();
    const rimPosition = rimGeometry.attributes.position as THREE.BufferAttribute;
    rimLevels.forEach((level, index) => rimPosition.setY(index, heightOf(level, scale) + 0.02));
    rimPosition.needsUpdate = true;
    displayedRelief = scale;
    placeMarker(hoverMarker, hoverMarker.cell);
    placeMarker(selectedMarker, selectedMarker.cell);
  };

  // Picking: first surface hit whose UV falls inside India (the mask only hides pixels, it doesn't stop rays).
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const pick = (clientX: number, clientY: number): Cell | null => {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.set(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    for (const hit of raycaster.intersectObject(surface, false)) {
      if (!hit.uv) continue;
      const longitude = extent.west + hit.uv.x * (extent.east - extent.west);
      const latitude = extent.south + hit.uv.y * (extent.north - extent.south);
      if (!insideIndia(mask, longitude, latitude)) continue;
      const row = Math.max(0, Math.min(rows - 1, Math.round((latitude - extent.south) / latitudeStep)));
      const column = Math.max(0, Math.min(columns - 1, Math.round((longitude - extent.west) / longitudeStep)));
      return { row, column, value: values[row][column], latitude: latitudes[row], longitude: longitudes[column] };
    }
    return null;
  };
  let pendingPointer: { x: number; y: number } | null = null;
  let pressed: { x: number; y: number } | null = null;
  const onPointerMove = (event: PointerEvent) => {
    if (event.buttons) {
      pendingPointer = null;
      placeMarker(hoverMarker, null);
      events.onHover(null);
      return;
    }
    pendingPointer = { x: event.clientX, y: event.clientY };
  };
  const onPointerLeave = () => {
    pendingPointer = null;
    placeMarker(hoverMarker, null);
    events.onHover(null);
  };
  const onPointerDown = (event: PointerEvent) => { pressed = { x: event.clientX, y: event.clientY }; };
  const onPointerUp = (event: PointerEvent) => {
    if (!pressed || Math.hypot(event.clientX - pressed.x, event.clientY - pressed.y) > 5) return;
    pressed = null;
    const cell = pick(event.clientX, event.clientY);
    if (!cell) return;
    placeMarker(selectedMarker, cell);
    events.onSelect(cell);
  };
  const canvas = renderer.domElement;
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerleave", onPointerLeave);
  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointerup", onPointerUp);

  controls.addEventListener("change", () => { dirty = true; });
  const resize = () => {
    const width = container.clientWidth;
    const height = container.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    dirty = true;
  };
  const observer = new ResizeObserver(resize);
  observer.observe(container);
  resize();

  // Narrow canvases crop the horizontal field of view, so pull the camera back until India fits.
  const fitted = (view: View) => views[view].position.clone().multiplyScalar(Math.max(1, 1.05 / camera.aspect));
  let flight: { fromPosition: THREE.Vector3; fromTarget: THREE.Vector3; toPosition: THREE.Vector3; to: View; start: number; duration: number } | null = null;
  const fly = (view: View, duration = 900) => {
    flight = { fromPosition: camera.position.clone(), fromTarget: controls.target.clone(), toPosition: fitted(view), to: view, start: performance.now(), duration };
  };
  camera.position.copy(fitted(reducedMotion ? "default" : "top")).multiplyScalar(reducedMotion ? 1 : 1.25);
  controls.target.copy(views.default.target);
  if (!reducedMotion) fly("default", 1700);
  const introStart = performance.now();
  let introDone = reducedMotion;

  const ease = (t: number) => 1 - Math.pow(1 - t, 3);
  let frame = 0;
  const animate = (now: number) => {
    frame = requestAnimationFrame(animate);
    const animating = !introDone || flight !== null || controls.autoRotate || selectedMarker.group.visible;
    if (!introDone) {
      const t = Math.min(1, (now - introStart) / 1500);
      applyRelief(relief * ease(t));
      introDone = t === 1;
    }
    if (flight) {
      const t = Math.min(1, (now - flight.start) / flight.duration);
      camera.position.lerpVectors(flight.fromPosition, flight.toPosition, ease(t));
      controls.target.lerpVectors(flight.fromTarget, views[flight.to].target, ease(t));
      if (t === 1) flight = null;
    }
    if (pendingPointer) {
      const { x, y } = pendingPointer;
      pendingPointer = null;
      const cell = pick(x, y);
      placeMarker(hoverMarker, cell);
      dirty = true;
      const rect = container.getBoundingClientRect();
      events.onHover(cell ? { ...cell, x: x - rect.left, y: y - rect.top, flip: x - rect.left > rect.width - 170 } : null);
    }
    const pulse = 1 + Math.sin(now / 280) * 0.18;
    selectedMarker.halo.scale.setScalar(pulse);
    const moved = controls.update();
    if (!animating && !moved && !dirty) return;
    dirty = false;
    renderer.render(scene, camera);
  };
  frame = requestAnimationFrame(animate);

  return {
    setRelief: (next) => {
      relief = next;
      if (introDone) applyRelief(next);
      dirty = true;
    },
    setSpin: (spin) => { controls.autoRotate = spin; dirty = true; },
    fly: (view) => fly(view),
    dispose: () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerleave", onPointerLeave);
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointerup", onPointerUp);
      scene.traverse((object) => {
        const mesh = object as THREE.Mesh;
        mesh.geometry?.dispose();
        (Array.isArray(mesh.material) ? mesh.material : mesh.material ? [mesh.material] : []).forEach((material) => material.dispose());
      });
      maskTexture.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      canvas.remove();
    },
  };
}
