import { useState, useEffect, useRef, useCallback, useReducer } from "react";

// ── Theme ─────────────────────────────────────────────────────────────────────
const T = {
  bg: "#080c10", bg2: "#0e1420", bg3: "#141c2c", bg4: "#1e2a3e",
  border: "#1e2d45", fg: "#e8f4ff", fg2: "#7a9cc5", fg3: "#3a5070",
  acc: "#2d7ff9", acc2: "#0d5fd4", green: "#1db954", greenBg: "#0a1f12",
  red: "#e03e3e", redBg: "#1f0a0a", yellow: "#f5a623", yellowBg: "#1f1400",
  purple: "#9b59f7", cyan: "#00d4ff", orange: "#ff6b35",
};

// ── Step Definitions ──────────────────────────────────────────────────────────
const STEP_TYPES = {
  click:        { icon: "🖱", label: "Click",           color: T.acc,    cat: "Mouse" },
  double_click: { icon: "🖱", label: "Double Click",    color: T.acc,    cat: "Mouse" },
  right_click:  { icon: "🖱", label: "Right Click",     color: T.purple, cat: "Mouse" },
  mouse_move:   { icon: "➤", label: "Move Mouse",       color: T.cyan,   cat: "Mouse" },
  scroll:       { icon: "↕", label: "Scroll",            color: T.fg2,    cat: "Mouse" },
  clear_field:  { icon: "⌫", label: "Clear Field",      color: T.yellow, cat: "Mouse" },
  hotkey:       { icon: "⌨", label: "Hotkey",           color: "#f78166",cat: "Keys"  },
  type_text:    { icon: "✍", label: "Type Text",         color: T.green,  cat: "Keys"  },
  clip_type:    { icon: "📋", label: "Clip Type",        color: T.green,  cat: "Keys"  },
  key_repeat:   { icon: "🔁", label: "Key Repeat",       color: "#f78166",cat: "Keys"  },
  hold_key:     { icon: "⏱", label: "Hold Key",          color: T.orange, cat: "Keys"  },
  wait:         { icon: "⏳", label: "Wait",              color: T.fg2,    cat: "Flow"  },
  loop:         { icon: "🔄", label: "Loop",              color: T.yellow, cat: "Flow"  },
  pagedown:     { icon: "⬇", label: "Page Down",         color: T.fg2,    cat: "Flow"  },
  pageup:       { icon: "⬆", label: "Page Up",           color: T.fg2,    cat: "Flow"  },
  screenshot:   { icon: "📸", label: "Screenshot",       color: T.purple, cat: "Utils" },
  condition:    { icon: "❓", label: "Check Window",     color: T.cyan,   cat: "Utils" },
  comment:      { icon: "💬", label: "Comment",          color: T.fg3,    cat: "Utils" },
};

const STEP_CATS = ["Mouse", "Keys", "Flow", "Utils"];

const TEMPLATES = [
  { name: "WhatsApp Send",  icon: "💬", desc: "Open chat, type & send",
    steps: [{type:"click",x:0,y:0,note:"Click message box"},{type:"clip_type",text:"{name}",note:"Type message"},{type:"hotkey",keys:"enter",note:"Send"},{type:"wait",seconds:1}] },
  { name: "Fill & Save",    icon: "📝", desc: "Clear, fill, save form",
    steps: [{type:"click",x:0,y:0,note:"Click field"},{type:"clear_field",x:0,y:0,note:"Clear"},{type:"clip_type",text:"{name}",note:"Fill"},{type:"hotkey",keys:"ctrl+s",note:"Save"},{type:"wait",seconds:1.5}] },
  { name: "Search & Open",  icon: "🔍", desc: "Click, search, Enter",
    steps: [{type:"click",x:0,y:0,note:"Search box"},{type:"clear_field",x:0,y:0,note:"Clear"},{type:"clip_type",text:"{name}",note:"Type"},{type:"hotkey",keys:"enter",note:"Search"},{type:"wait",seconds:2}] },
  { name: "Print Record",   icon: "🖨", desc: "Select record and print",
    steps: [{type:"click",x:0,y:0,note:"Click item"},{type:"wait",seconds:1},{type:"hotkey",keys:"ctrl+p",note:"Print"},{type:"hotkey",keys:"enter",note:"Confirm"},{type:"wait",seconds:2}] },
];

// ── Default step fields ───────────────────────────────────────────────────────
const stepDefault = (type) => {
  const base = { type, note: "", enabled: true };
  if (["click","double_click","right_click","mouse_move","clear_field"].includes(type)) return {...base,x:0,y:0};
  if (type==="scroll")    return {...base,x:0,y:0,direction:"down",clicks:3};
  if (type==="hotkey")    return {...base,keys:"enter"};
  if (["type_text","clip_type"].includes(type)) return {...base,text:"{name}"};
  if (type==="wait")      return {...base,seconds:1.0};
  if (["pagedown","pageup"].includes(type)) return {...base,times:1};
  if (type==="key_repeat") return {...base,key:"tab",times:1};
  if (type==="hold_key")  return {...base,key:"space",seconds:1.0};
  if (type==="loop")      return {...base,times:2,steps:[]};
  if (type==="screenshot") return {...base,folder:"screenshots"};
  if (type==="condition") return {...base,window_title:"",action:"skip"};
  if (type==="comment")   return {...base,text:""};
  return base;
};

const stepSummary = (s) => {
  if (["click","double_click","right_click","mouse_move","clear_field"].includes(s.type))
    return `(${s.x??0}, ${s.y??0})`;
  if (s.type==="scroll") return `${s.direction} ×${s.clicks}`;
  if (s.type==="hotkey") return s.keys||"";
  if (["type_text","clip_type"].includes(s.type)) return (s.text||"").slice(0,30);
  if (s.type==="wait") return `${s.seconds}s`;
  if (["pagedown","pageup"].includes(s.type)) return `×${s.times}`;
  if (s.type==="key_repeat") return `${s.key} ×${s.times}`;
  if (s.type==="hold_key") return `hold ${s.key} ${s.seconds}s`;
  if (s.type==="loop") return `×${s.times} (${(s.steps||[]).length} inner)`;
  if (s.type==="screenshot") return s.folder||"";
  if (s.type==="condition") return s.window_title||"";
  if (s.type==="comment") return (s.text||"").slice(0,30);
  return "";
};

// ── UUID helper ───────────────────────────────────────────────────────────────
let _uid = 0;
const uid = () => `s${++_uid}`;

const addIds = (steps) => steps.map(s => ({...s, _id: s._id || uid(), steps: s.steps ? addIds(s.steps) : undefined}));

// ── Flow reducer ──────────────────────────────────────────────────────────────
const MAX_UNDO = 40;
function flowReducer(state, action) {
  const push = (steps) => {
    const history = [...state.history.slice(-MAX_UNDO), state.steps];
    return { steps, history, future: [] };
  };
  switch (action.type) {
    case "SET":       return push(addIds(action.steps));
    case "ADD":       return push([...state.steps, {...stepDefault(action.st), _id: uid()}]);
    case "DEL":       return push(state.steps.filter(s=>s._id!==action.id));
    case "UPDATE":    return push(state.steps.map(s=>s._id===action.id ? {...s,...action.data} : s));
    case "MOVE": {
      const arr=[...state.steps], {from,to}=action;
      const [el]=arr.splice(from,1); arr.splice(to,0,el);
      return push(arr);
    }
    case "DUP": {
      const i=state.steps.findIndex(s=>s._id===action.id);
      const copy={...state.steps[i],_id:uid()};
      const arr=[...state.steps]; arr.splice(i+1,0,copy);
      return push(arr);
    }
    case "TOGGLE":    return push(state.steps.map(s=>s._id===action.id?{...s,enabled:!s.enabled}:s));
    case "CLEAR":     return push([]);
    case "LOAD":      return {steps:addIds(action.steps),history:[],future:[]};
    case "UNDO":
      if(!state.history.length) return state;
      return {steps:state.history[state.history.length-1], history:state.history.slice(0,-1), future:[state.steps,...state.future]};
    case "REDO":
      if(!state.future.length) return state;
      return {steps:state.future[0], history:[...state.history,state.steps], future:state.future.slice(1)};
    default: return state;
  }
}

// ── Styles ────────────────────────────────────────────────────────────────────
const G = {
  card: { background: T.bg2, border: `1px solid ${T.border}`, borderRadius: 10, overflow: "hidden" },
  btn:  (bg=T.bg3, fg=T.fg2) => ({ background:bg, color:fg, border:"none", borderRadius:6, cursor:"pointer", fontFamily:"inherit", fontSize:12, padding:"6px 12px", transition:"all 0.15s" }),
  input: { background:T.bg3, color:T.fg, border:`1px solid ${T.border}`, borderRadius:6, padding:"6px 10px", fontFamily:"'Fira Code', monospace", fontSize:12, outline:"none", width:"100%", boxSizing:"border-box" },
};

// ── CSS Injection ─────────────────────────────────────────────────────────────
const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap');
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:${T.bg}; color:${T.fg}; font-family:'Space Grotesk',sans-serif; overflow:hidden; }
  ::-webkit-scrollbar { width:6px; height:6px; }
  ::-webkit-scrollbar-track { background:${T.bg}; }
  ::-webkit-scrollbar-thumb { background:${T.border}; border-radius:3px; }
  ::-webkit-scrollbar-thumb:hover { background:${T.fg3}; }
  
  .rpa-root { display:flex; height:100vh; overflow:hidden; }
  .sidebar { width:220px; min-width:220px; background:${T.bg2}; border-right:1px solid ${T.border}; display:flex; flex-direction:column; padding:16px 0; gap:2px; }
  .sidebar-logo { padding:0 20px 16px; border-bottom:1px solid ${T.border}; margin-bottom:8px; }
  .sidebar-logo h1 { font-size:16px; font-weight:700; color:${T.fg}; letter-spacing:-0.5px; }
  .sidebar-logo span { font-size:10px; color:${T.fg3}; font-family:'Fira Code',monospace; }
  .nav-item { display:flex; align-items:center; gap:10px; padding:9px 20px; cursor:pointer; color:${T.fg2}; font-size:13px; font-weight:500; border-radius:0; transition:all 0.15s; border-left:3px solid transparent; }
  .nav-item:hover { background:${T.bg3}; color:${T.fg}; }
  .nav-item.active { background:${T.bg3}; color:${T.acc}; border-left-color:${T.acc}; }
  .nav-item .icon { font-size:15px; width:20px; text-align:center; }
  
  .main { flex:1; display:flex; flex-direction:column; overflow:hidden; }
  .topbar { height:52px; background:${T.bg2}; border-bottom:1px solid ${T.border}; display:flex; align-items:center; padding:0 20px; gap:12px; flex-shrink:0; }
  .topbar-title { font-size:14px; font-weight:600; color:${T.fg}; flex:1; }
  .content { flex:1; overflow-y:auto; padding:20px; }
  
  .tab-panel { display:none; } .tab-panel.active { display:block; }
  
  /* Buttons */
  .btn { border:none; border-radius:6px; cursor:pointer; font-family:inherit; font-size:12px; font-weight:500; padding:7px 14px; transition:all 0.15s; display:inline-flex; align-items:center; gap:6px; }
  .btn:hover { filter:brightness(1.15); }
  .btn:active { transform:scale(0.97); }
  .btn-primary { background:${T.acc}; color:#fff; }
  .btn-danger { background:${T.red}; color:#fff; }
  .btn-success { background:${T.green}; color:#fff; }
  .btn-ghost { background:${T.bg3}; color:${T.fg2}; border:1px solid ${T.border}; }
  .btn-ghost:hover { color:${T.fg}; background:${T.bg4}; }
  .btn-warning { background:${T.yellow}; color:#000; }
  .btn-sm { padding:4px 9px; font-size:11px; }
  .btn-xs { padding:2px 6px; font-size:10px; }
  .btn:disabled { opacity:0.4; cursor:not-allowed; filter:none; }
  
  /* Step cards */
  .step-card { display:flex; align-items:center; gap:0; background:${T.bg2}; border:1px solid ${T.border}; border-radius:8px; margin-bottom:6px; overflow:hidden; transition:all 0.15s; }
  .step-card:hover { border-color:${T.fg3}; }
  .step-card.disabled-step { opacity:0.45; }
  .step-card.dragging { opacity:0.4; transform:scale(0.98); }
  .step-card.drag-over { border-color:${T.acc}; }
  .step-handle { width:28px; min-width:28px; background:${T.bg3}; display:flex; align-items:center; justify-content:center; cursor:grab; color:${T.fg3}; font-size:14px; align-self:stretch; transition:background 0.15s; }
  .step-handle:hover { background:${T.bg4}; color:${T.fg2}; }
  .step-accent { width:4px; min-width:4px; align-self:stretch; }
  .step-body { flex:1; padding:9px 12px; min-width:0; }
  .step-type-row { display:flex; align-items:center; gap:8px; }
  .step-type-label { font-size:11px; font-weight:600; }
  .step-summary { font-family:'Fira Code',monospace; font-size:11px; color:${T.fg2}; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:300px; }
  .step-note { font-size:10px; color:${T.fg3}; margin-top:2px; }
  .step-actions { display:flex; align-items:center; gap:2px; padding:0 8px; }
  .step-act-btn { background:none; border:none; cursor:pointer; color:${T.fg3}; font-size:12px; padding:4px; border-radius:4px; transition:all 0.12s; }
  .step-act-btn:hover { background:${T.bg3}; color:${T.fg}; }
  .step-num { font-family:'Fira Code',monospace; font-size:10px; color:${T.fg3}; min-width:24px; text-align:right; }
  
  /* Input/field */
  input, select, textarea { background:${T.bg3}; color:${T.fg}; border:1px solid ${T.border}; border-radius:6px; padding:7px 10px; font-family:'Fira Code',monospace; font-size:12px; outline:none; width:100%; transition:border 0.15s; }
  input:focus, select:focus, textarea:focus { border-color:${T.acc}; }
  select { cursor:pointer; }
  label { font-size:12px; color:${T.fg2}; display:block; margin-bottom:4px; font-weight:500; }
  
  /* Grid layout for fields */
  .field-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  .field-group { margin-bottom:12px; }
  .field-group.full { grid-column:1/-1; }
  
  /* Panels */
  .panel { background:${T.bg2}; border:1px solid ${T.border}; border-radius:10px; padding:16px; margin-bottom:16px; }
  .panel-title { font-size:13px; font-weight:600; color:${T.fg}; margin-bottom:12px; display:flex; align-items:center; gap:8px; }
  
  /* Log */
  .log-box { background:#050810; border:1px solid ${T.border}; border-radius:8px; font-family:'Fira Code',monospace; font-size:11px; padding:12px; height:280px; overflow-y:auto; }
  .log-line { padding:1px 0; line-height:1.7; }
  .log-ok { color:${T.green}; }
  .log-err { color:${T.red}; }
  .log-warn { color:${T.yellow}; }
  .log-dim { color:${T.fg3}; }
  .log-head { color:${T.acc}; }
  
  /* Run status */
  .progress-bar { height:4px; background:${T.bg3}; border-radius:2px; overflow:hidden; margin:8px 0; }
  .progress-fill { height:100%; background:${T.green}; border-radius:2px; transition:width 0.3s; }
  
  /* Badge */
  .badge { display:inline-flex; align-items:center; padding:2px 8px; border-radius:12px; font-size:10px; font-weight:600; }
  
  /* Tags */
  .tag { display:inline-flex; align-items:center; gap:4px; padding:2px 8px; border-radius:12px; font-size:10px; background:${T.bg3}; color:${T.fg2}; border:1px solid ${T.border}; cursor:pointer; transition:all 0.12s; }
  .tag:hover { background:${T.bg4}; color:${T.fg}; }
  .tag.active { background:${T.acc}; color:#fff; border-color:${T.acc}; }
  
  /* Modal */
  .modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,0.7); z-index:1000; display:flex; align-items:center; justify-content:center; backdrop-filter:blur(4px); }
  .modal { background:${T.bg2}; border:1px solid ${T.border}; border-radius:12px; width:520px; max-width:95vw; max-height:90vh; overflow-y:auto; }
  .modal-header { padding:16px 20px; border-bottom:1px solid ${T.border}; display:flex; align-items:center; justify-content:space-between; }
  .modal-title { font-size:14px; font-weight:600; color:${T.fg}; }
  .modal-body { padding:20px; }
  .modal-footer { padding:12px 20px; border-top:1px solid ${T.border}; display:flex; gap:8px; justify-content:flex-end; }
  
  /* Name list */
  .name-chip { display:inline-flex; align-items:center; gap:6px; background:${T.bg3}; border:1px solid ${T.border}; border-radius:6px; padding:4px 10px; font-size:12px; color:${T.fg2}; margin:3px; }
  .name-chip-remove { cursor:pointer; color:${T.fg3}; font-size:10px; }
  .name-chip-remove:hover { color:${T.red}; }
  
  /* Tooltip */
  .tooltip-wrap { position:relative; display:inline-flex; }
  .tooltip-body { position:absolute; bottom:calc(100% + 6px); left:50%; transform:translateX(-50%); background:${T.bg4}; color:${T.fg}; font-size:10px; padding:4px 8px; border-radius:4px; white-space:nowrap; pointer-events:none; opacity:0; transition:opacity 0.15s; z-index:100; border:1px solid ${T.border}; }
  .tooltip-wrap:hover .tooltip-body { opacity:1; }
  
  /* Switch */
  .switch { position:relative; width:36px; height:20px; cursor:pointer; }
  .switch input { opacity:0; width:0; height:0; }
  .switch-slider { position:absolute; inset:0; background:${T.bg3}; border-radius:10px; transition:background 0.2s; border:1px solid ${T.border}; }
  .switch-slider:before { content:""; position:absolute; width:14px; height:14px; left:2px; top:2px; background:${T.fg3}; border-radius:50%; transition:transform 0.2s,background 0.2s; }
  input:checked + .switch-slider { background:${T.acc}; border-color:${T.acc}; }
  input:checked + .switch-slider:before { transform:translateX(16px); background:#fff; }
  
  /* Divider */
  .divider { height:1px; background:${T.border}; margin:16px 0; }
  
  /* Section header */
  .section-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; }
  
  /* Stat card */
  .stat-card { background:${T.bg2}; border:1px solid ${T.border}; border-radius:8px; padding:14px 16px; }
  .stat-value { font-size:24px; font-weight:700; color:${T.fg}; font-variant-numeric:tabular-nums; }
  .stat-label { font-size:11px; color:${T.fg3}; margin-top:2px; }
  
  /* Animate */
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
  @keyframes slide-in { from{transform:translateY(8px);opacity:0} to{transform:none;opacity:1} }
  .animate-pulse { animation:pulse 1.5s ease-in-out infinite; }
  .slide-in { animation:slide-in 0.2s ease; }
  
  /* Scrollable step list */
  .step-list { max-height:calc(100vh - 320px); overflow-y:auto; padding-right:2px; }
  
  /* Name textarea */
  .name-textarea { width:100%; height:180px; resize:vertical; }
  
  /* Tab row */
  .tab-row { display:flex; gap:4px; margin-bottom:16px; flex-wrap:wrap; }
  .tab-btn { background:${T.bg3}; color:${T.fg2}; border:1px solid ${T.border}; border-radius:6px; padding:6px 14px; font-size:12px; cursor:pointer; font-family:inherit; transition:all 0.15s; }
  .tab-btn.active { background:${T.acc}; color:#fff; border-color:${T.acc}; }
  .tab-btn:hover:not(.active) { background:${T.bg4}; color:${T.fg}; }
  
  /* Drag-over indicator line */
  .drop-line { height:3px; background:${T.acc}; border-radius:2px; margin:-3px 0 3px; }
  
  /* Import/Export JSON */
  .code-block { background:${T.bg}; border:1px solid ${T.border}; border-radius:6px; padding:12px; font-family:'Fira Code',monospace; font-size:11px; color:${T.fg2}; overflow-x:auto; white-space:pre; max-height:300px; overflow-y:auto; }
  
  /* RPA simulator */
  .simulator { background:${T.bg}; border:1px solid ${T.border}; border-radius:8px; padding:16px; font-family:'Fira Code',monospace; font-size:11px; color:${T.green}; height:200px; overflow-y:auto; }
  
  /* Search */
  .search-input { position:relative; }
  .search-input input { padding-left:28px; }
  .search-icon { position:absolute; left:9px; top:50%; transform:translateY(-50%); color:${T.fg3}; font-size:12px; pointer-events:none; }
  
  /* Two-col layout */
  .two-col { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
  .three-col { display:grid; grid-template-columns:1fr 1fr 1fr; gap:16px; }
  .four-col { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
  
  /* Variable chip */
  .var-row { display:flex; align-items:center; gap:8px; padding:8px 12px; background:${T.bg3}; border-radius:6px; margin-bottom:6px; border:1px solid ${T.border}; }
  
  /* Copy btn animation */
  @keyframes flash { 0%,100%{background:${T.bg3}} 50%{background:${T.green}} }
  .copy-flash { animation:flash 0.4s; }

  /* Rec indicator */
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
  .rec-dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:${T.red}; animation:blink 1s infinite; }
  
  /* Settings section */
  .settings-section { margin-bottom:24px; }
  .settings-section-title { font-size:12px; font-weight:600; color:${T.fg3}; text-transform:uppercase; letter-spacing:0.8px; margin-bottom:10px; }
  
  /* Responsive */
  @media(max-width:900px){ .sidebar{width:60px;} .sidebar .nav-item span{display:none;} .sidebar-logo h1,.sidebar-logo span{display:none;} }
`;

// ── Tooltip ───────────────────────────────────────────────────────────────────
const Tip = ({text, children}) => (
  <div className="tooltip-wrap">
    {children}
    <div className="tooltip-body">{text}</div>
  </div>
);

// ── Switch ────────────────────────────────────────────────────────────────────
const Switch = ({checked, onChange}) => (
  <label className="switch">
    <input type="checkbox" checked={checked} onChange={e=>onChange(e.target.checked)} />
    <span className="switch-slider" />
  </label>
);

// ── Modal ─────────────────────────────────────────────────────────────────────
const Modal = ({title, onClose, children, footer}) => (
  <div className="modal-overlay" onClick={e=>e.target===e.currentTarget&&onClose()}>
    <div className="modal slide-in">
      <div className="modal-header">
        <span className="modal-title">{title}</span>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
      </div>
      <div className="modal-body">{children}</div>
      {footer && <div className="modal-footer">{footer}</div>}
    </div>
  </div>
);

// ── StepEditor Modal ──────────────────────────────────────────────────────────
const StepEditor = ({step, onSave, onClose}) => {
  const [data, setData] = useState({...step});
  const s = STEP_TYPES[step.type];
  const set = (k,v) => setData(d=>({...d,[k]:v}));

  const xy = (k) => (
    <div style={{display:"flex",gap:8}}>
      <div>
        <label>X</label>
        <input type="number" value={data.x??0} onChange={e=>set("x",+e.target.value)} style={{width:80}} />
      </div>
      <div>
        <label>Y</label>
        <input type="number" value={data.y??0} onChange={e=>set("y",+e.target.value)} style={{width:80}} />
      </div>
    </div>
  );

  return (
    <Modal title={`${s?.icon} Edit: ${s?.label}`} onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={()=>onSave(data)}>Save Step</button>
      </>}>
      <div style={{display:"flex",flexDirection:"column",gap:12}}>
        {/* Coord steps */}
        {["click","double_click","right_click","mouse_move","clear_field"].includes(step.type) && xy()}
        {step.type==="scroll" && <>
          {xy()}
          <div className="field-grid">
            <div><label>Direction</label>
              <select value={data.direction||"down"} onChange={e=>set("direction",e.target.value)}>
                <option>down</option><option>up</option></select></div>
            <div><label>Clicks</label>
              <input type="number" value={data.clicks??3} onChange={e=>set("clicks",+e.target.value)} /></div>
          </div>
        </>}
        {step.type==="hotkey" && <div><label>Keys (e.g. ctrl+s, enter, alt+f4)</label>
          <input value={data.keys||""} onChange={e=>set("keys",e.target.value)} /></div>}
        {["type_text","clip_type"].includes(step.type) && <div><label>Text ({"{name}"} = current name)</label>
          <textarea rows={3} value={data.text||""} onChange={e=>set("text",e.target.value)} /></div>}
        {step.type==="wait" && <div><label>Seconds</label>
          <input type="number" step="0.5" value={data.seconds??1} onChange={e=>set("seconds",+e.target.value)} /></div>}
        {["pagedown","pageup"].includes(step.type) && <div><label>Times</label>
          <input type="number" value={data.times??1} onChange={e=>set("times",+e.target.value)} /></div>}
        {step.type==="key_repeat" && <div className="field-grid">
          <div><label>Key</label><input value={data.key||"tab"} onChange={e=>set("key",e.target.value)} /></div>
          <div><label>Times</label><input type="number" value={data.times??1} onChange={e=>set("times",+e.target.value)} /></div>
        </div>}
        {step.type==="hold_key" && <div className="field-grid">
          <div><label>Key</label><input value={data.key||"space"} onChange={e=>set("key",e.target.value)} /></div>
          <div><label>Seconds</label><input type="number" step="0.1" value={data.seconds??1} onChange={e=>set("seconds",+e.target.value)} /></div>
        </div>}
        {step.type==="loop" && <div><label>Repeat N times</label>
          <input type="number" value={data.times??2} onChange={e=>set("times",+e.target.value)} /></div>}
        {step.type==="screenshot" && <div><label>Folder path</label>
          <input value={data.folder||"screenshots"} onChange={e=>set("folder",e.target.value)} /></div>}
        {step.type==="condition" && <>
          <div><label>Window title must contain</label>
            <input value={data.window_title||""} onChange={e=>set("window_title",e.target.value)} /></div>
          <div><label>If not found</label>
            <select value={data.action||"skip"} onChange={e=>set("action",e.target.value)}>
              <option>skip</option><option>stop</option></select></div>
        </>}
        {step.type==="comment" && <div><label>Comment text</label>
          <textarea rows={2} value={data.text||""} onChange={e=>set("text",e.target.value)} /></div>}
        <div className="divider" />
        <div><label>Note / Label</label>
          <input value={data.note||""} onChange={e=>set("note",e.target.value)} placeholder="Optional label" /></div>
        <div style={{display:"flex",alignItems:"center",gap:10}}>
          <Switch checked={data.enabled!==false} onChange={v=>set("enabled",v)} />
          <span style={{fontSize:12,color:T.fg2}}>Step enabled</span>
        </div>
      </div>
    </Modal>
  );
};

// ── Step Card ─────────────────────────────────────────────────────────────────
const StepCard = ({step, index, total, onEdit, onDel, onDup, onMove, onToggle, dragHandlers}) => {
  const info = STEP_TYPES[step.type] || {icon:"•",label:step.type,color:T.fg2};
  const enabled = step.enabled !== false;

  return (
    <div className={`step-card${!enabled?" disabled-step":""}`}
      draggable {...dragHandlers(index)}>
      <div className="step-handle" title="Drag to reorder">⠿</div>
      <div className="step-accent" style={{background:info.color}} />
      <div className="step-num">{index+1}</div>
      <div className="step-body">
        <div className="step-type-row">
          <span>{info.icon}</span>
          <span className="step-type-label" style={{color:info.color}}>{info.label}</span>
          <span className="step-summary">{stepSummary(step)}</span>
        </div>
        {step.note && <div className="step-note">// {step.note}</div>}
      </div>
      <div className="step-actions">
        <button className="step-act-btn" title={enabled?"Disable":"Enable"} onClick={()=>onToggle(step._id)}>{enabled?"👁":"⊘"}</button>
        <button className="step-act-btn" title="Edit" onClick={()=>onEdit(step._id)}>✏</button>
        <button className="step-act-btn" title="Duplicate" onClick={()=>onDup(step._id)}>⧉</button>
        <button className="step-act-btn" title="Move up" onClick={()=>onMove(index,index-1)} disabled={index===0} style={{opacity:index===0?0.3:1}}>▲</button>
        <button className="step-act-btn" title="Move down" onClick={()=>onMove(index,index+1)} disabled={index===total-1} style={{opacity:index===total-1?0.3:1}}>▼</button>
        <button className="step-act-btn" title="Delete" onClick={()=>onDel(step._id)} style={{color:T.red}}>✕</button>
      </div>
    </div>
  );
};

// ── Step Picker ───────────────────────────────────────────────────────────────
const StepPicker = ({onPick, onClose}) => {
  const [cat, setCat] = useState("Mouse");
  const [search, setSearch] = useState("");
  const types = Object.entries(STEP_TYPES).filter(([t,info])=>
    info.cat===cat && (!search || info.label.toLowerCase().includes(search.toLowerCase()) || t.includes(search))
  );
  return (
    <Modal title="Add a Step" onClose={onClose}>
      <div className="search-input" style={{marginBottom:12,position:"relative"}}>
        <span className="search-icon">🔍</span>
        <input placeholder="Search steps…" value={search} onChange={e=>setSearch(e.target.value)} style={{paddingLeft:28}} autoFocus />
      </div>
      <div style={{display:"flex",gap:6,marginBottom:14,flexWrap:"wrap"}}>
        {STEP_CATS.map(c=>(
          <button key={c} className={`tab-btn${cat===c?" active":""}`} onClick={()=>setCat(c)}>{c}</button>
        ))}
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
        {(search ? Object.entries(STEP_TYPES).filter(([t,i])=>i.label.toLowerCase().includes(search.toLowerCase())||t.includes(search)) : types)
          .map(([type,info])=>(
          <button key={type} onClick={()=>{onPick(type);onClose();}}
            style={{background:T.bg3,border:`1px solid ${T.border}`,borderRadius:8,padding:"10px 12px",cursor:"pointer",textAlign:"left",display:"flex",alignItems:"center",gap:10,transition:"all 0.15s"}}
            onMouseEnter={e=>e.currentTarget.style.borderColor=info.color}
            onMouseLeave={e=>e.currentTarget.style.borderColor=T.border}>
            <span style={{fontSize:18}}>{info.icon}</span>
            <span style={{color:info.color,fontWeight:600,fontSize:12,fontFamily:"Space Grotesk"}}>{info.label}</span>
          </button>
        ))}
      </div>
    </Modal>
  );
};

// ── Flow Panel ────────────────────────────────────────────────────────────────
const FlowPanel = ({state, dispatch, label}) => {
  const [showPicker, setShowPicker] = useState(false);
  const [editId, setEditId] = useState(null);
  const [search, setSearch] = useState("");
  const [dragFrom, setDragFrom] = useState(null);
  const [dragOver, setDragOver] = useState(null);

  const editStep = state.steps.find(s=>s._id===editId);

  const filtered = search
    ? state.steps.filter(s=>{
        const info = STEP_TYPES[s.type];
        return (info?.label||s.type).toLowerCase().includes(search.toLowerCase())
          || stepSummary(s).toLowerCase().includes(search.toLowerCase())
          || (s.note||"").toLowerCase().includes(search.toLowerCase());
      })
    : state.steps;

  const dragHandlers = (idx) => ({
    onDragStart: ()=>setDragFrom(idx),
    onDragEnd: ()=>{setDragFrom(null);setDragOver(null);},
    onDragOver: (e)=>{e.preventDefault();setDragOver(idx);},
    onDrop: ()=>{
      if(dragFrom!==null&&dragOver!==null&&dragFrom!==dragOver)
        dispatch({type:"MOVE",from:dragFrom,to:dragOver});
      setDragFrom(null);setDragOver(null);
    },
  });

  return (
    <div>
      {/* Toolbar */}
      <div style={{display:"flex",gap:8,marginBottom:12,flexWrap:"wrap",alignItems:"center"}}>
        <button className="btn btn-primary btn-sm" onClick={()=>setShowPicker(true)}>＋ Add Step</button>
        <Tip text="Undo (Ctrl+Z)"><button className="btn btn-ghost btn-sm" onClick={()=>dispatch({type:"UNDO"})} disabled={!state.history.length}>↩ Undo</button></Tip>
        <Tip text="Redo"><button className="btn btn-ghost btn-sm" onClick={()=>dispatch({type:"REDO"})} disabled={!state.future.length}>↪ Redo</button></Tip>
        <div className="search-input" style={{position:"relative",flex:1,minWidth:120,maxWidth:200}}>
          <span className="search-icon">🔍</span>
          <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Filter steps…" style={{paddingLeft:26,height:30,fontSize:11}} />
        </div>
        <span style={{fontSize:11,color:T.fg3,marginLeft:"auto"}}>{state.steps.length} steps</span>
        {state.steps.length>0&&<button className="btn btn-ghost btn-sm" style={{color:T.red}} onClick={()=>{if(confirm("Clear all steps?"))dispatch({type:"CLEAR"})}}>🗑 Clear</button>}
      </div>

      {/* Templates */}
      <div style={{display:"flex",gap:6,marginBottom:12,flexWrap:"wrap"}}>
        {TEMPLATES.map(t=>(
          <button key={t.name} className="btn btn-ghost btn-xs"
            onClick={()=>{if(state.steps.length===0||confirm("Replace steps with template?"))dispatch({type:"LOAD",steps:t.steps})}}
            title={t.desc}>
            {t.icon} {t.name}
          </button>
        ))}
      </div>

      {/* Step list */}
      <div className="step-list">
        {filtered.length===0 ? (
          <div style={{textAlign:"center",padding:"40px 0",color:T.fg3}}>
            <div style={{fontSize:32,marginBottom:8}}>📋</div>
            <div style={{fontSize:13}}>No steps yet</div>
            <div style={{fontSize:11,marginTop:4}}>Click "＋ Add Step" or choose a template above</div>
          </div>
        ) : filtered.map((step,i)=>(
          <StepCard key={step._id} step={step} index={i} total={filtered.length}
            onEdit={setEditId} onDel={id=>dispatch({type:"DEL",id})}
            onDup={id=>dispatch({type:"DUP",id})} onToggle={id=>dispatch({type:"TOGGLE",id})}
            onMove={(f,t)=>{if(t>=0&&t<state.steps.length)dispatch({type:"MOVE",from:f,to:t})}}
            dragHandlers={dragHandlers} />
        ))}
      </div>

      {showPicker && <StepPicker onPick={t=>dispatch({type:"ADD",st:t})} onClose={()=>setShowPicker(false)} />}
      {editStep && <StepEditor step={editStep} onSave={data=>dispatch({type:"UPDATE",id:editId,data})} onClose={()=>setEditId(null)} />}
    </div>
  );
};

// ── Name List Panel ───────────────────────────────────────────────────────────
const NameListTab = ({names, setNames}) => {
  const [raw, setRaw] = useState(names.join("\n"));
  const [csvText, setCsvText] = useState("");
  const [view, setView] = useState("text"); // text | chips

  const sync = (v) => {
    setRaw(v);
    setNames(v.split("\n").map(n=>n.trim()).filter(Boolean));
  };
  const syncChips = (ns) => { setNames(ns); setRaw(ns.join("\n")); };

  const importCsv = () => {
    const ns = csvText.split(/[\n,;]/).map(n=>n.trim()).filter(Boolean);
    syncChips([...names, ...ns]);
    setCsvText("");
  };

  const shuffle = () => syncChips([...names].sort(()=>Math.random()-0.5));
  const dedupe  = () => syncChips([...new Set(names)]);
  const sort    = () => syncChips([...names].sort());

  return (
    <div>
      <div className="three-col" style={{marginBottom:16}}>
        <div className="stat-card"><div className="stat-value">{names.length}</div><div className="stat-label">Total Names</div></div>
        <div className="stat-card"><div className="stat-value">{new Set(names).size}</div><div className="stat-label">Unique Names</div></div>
        <div className="stat-card"><div className="stat-value">{names.length-new Set(names).size}</div><div className="stat-label">Duplicates</div></div>
      </div>

      <div className="panel">
        <div className="panel-title">Name List
          <div style={{marginLeft:"auto",display:"flex",gap:6}}>
            <Tip text="Shuffle order"><button className="btn btn-ghost btn-xs" onClick={shuffle}>🔀 Shuffle</button></Tip>
            <Tip text="Sort A→Z"><button className="btn btn-ghost btn-xs" onClick={sort}>↕ Sort</button></Tip>
            <Tip text="Remove duplicates"><button className="btn btn-ghost btn-xs" onClick={dedupe}>⊘ Dedupe</button></Tip>
            <button className="btn btn-ghost btn-xs" onClick={()=>setView(v=>v==="text"?"chips":"text")}>
              {view==="text"?"🏷 Chips":"📝 Text"}
            </button>
          </div>
        </div>
        {view==="text" ? (
          <textarea className="name-textarea" value={raw} onChange={e=>sync(e.target.value)}
            placeholder={"Enter names here, one per line:\nRam Bahadur\nSita Devi\nArjun Shah\n…"} />
        ) : (
          <div style={{minHeight:120,padding:8,background:T.bg3,borderRadius:6,border:`1px solid ${T.border}`}}>
            {names.map((n,i)=>(
              <span key={i} className="name-chip">{n}
                <span className="name-chip-remove" onClick={()=>syncChips(names.filter((_,j)=>j!==i))}>✕</span>
              </span>
            ))}
            {names.length===0&&<span style={{color:T.fg3,fontSize:12}}>No names yet — switch to Text view to add</span>}
          </div>
        )}
        <div style={{marginTop:8,fontSize:11,color:T.fg3}}>
          Tip: Use <code style={{color:T.cyan}}>{"{name}"}</code> in your steps — it gets replaced with each name.
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Import from CSV/Paste</div>
        <textarea rows={3} value={csvText} onChange={e=>setCsvText(e.target.value)}
          placeholder={"Paste CSV or names separated by commas, semicolons, or newlines…"} />
        <div style={{display:"flex",gap:8,marginTop:8}}>
          <button className="btn btn-primary btn-sm" onClick={importCsv} disabled={!csvText.trim()}>Import</button>
          <button className="btn btn-ghost btn-sm" onClick={()=>syncChips([])}>Clear All</button>
        </div>
      </div>
    </div>
  );
};

// ── Variables Panel ───────────────────────────────────────────────────────────
const VariablesPanel = ({vars, setVars}) => {
  const [newKey, setNewKey] = useState("");
  const [newVal, setNewVal] = useState("");
  const add = () => {
    if(!newKey.trim()) return;
    setVars(v=>({...v,[newKey.trim()]:newVal}));
    setNewKey(""); setNewVal("");
  };
  const del = (k) => setVars(v=>{ const n={...v}; delete n[k]; return n; });
  const update = (k,val) => setVars(v=>({...v,[k]:val}));

  return (
    <div>
      <div className="panel">
        <div className="panel-title">Variables
          <span style={{fontSize:11,color:T.fg3,fontWeight:400,marginLeft:4}}>— use {"{varname}"} in any step text</span>
        </div>
        {Object.entries(vars).map(([k,v])=>(
          <div key={k} className="var-row">
            <span style={{color:T.cyan,fontFamily:"'Fira Code',monospace",fontSize:12,minWidth:100}}>{`{${k}}`}</span>
            <input value={v} onChange={e=>update(k,e.target.value)} style={{flex:1}} />
            <button className="btn btn-ghost btn-xs" style={{color:T.red}} onClick={()=>del(k)}>✕</button>
          </div>
        ))}
        {Object.keys(vars).length===0&&<p style={{color:T.fg3,fontSize:12,margin:"8px 0"}}>No variables defined yet.</p>}
        <div className="divider" />
        <div style={{display:"flex",gap:8,alignItems:"center"}}>
          <div style={{flex:"0 0 120px"}}>
            <input value={newKey} onChange={e=>setNewKey(e.target.value)} placeholder="Variable name" onKeyDown={e=>e.key==="Enter"&&add()} />
          </div>
          <div style={{flex:1}}>
            <input value={newVal} onChange={e=>setNewVal(e.target.value)} placeholder="Default value" onKeyDown={e=>e.key==="Enter"&&add()} />
          </div>
          <button className="btn btn-primary btn-sm" onClick={add}>＋ Add</button>
        </div>
      </div>
      <div className="panel" style={{background:T.bg3,border:`1px solid ${T.border}`}}>
        <div style={{fontSize:12,color:T.fg2,lineHeight:1.7}}>
          <b style={{color:T.fg}}>How variables work:</b><br/>
          • Define <code style={{color:T.cyan}}>{"{url}"}</code>, <code style={{color:T.cyan}}>{"{password}"}</code>, etc. here<br/>
          • Use them in any Type Text or Clip Type step<br/>
          • <code style={{color:T.acc}}>{"{name}"}</code> is always auto-replaced from the Name List<br/>
          • Values are filled in before the run starts
        </div>
      </div>
    </div>
  );
};

// ── Run Panel ─────────────────────────────────────────────────────────────────
const RunTab = ({names, steps, vars, settings, setSettings}) => {
  const [running, setRunning] = useState(false);
  const [paused, setPaused] = useState(false);
  const [logs, setLogs] = useState([]);
  const [progress, setProgress] = useState({cur:0,total:0,name:""});
  const [stats, setStats] = useState({success:0,fail:0,elapsed:0});
  const [countdown, setCountdown] = useState(0);
  const stopRef = useRef(false);
  const pauseRef = useRef(false);
  const logRef = useRef(null);

  const addLog = useCallback((msg, tag="") => {
    setLogs(l=>[...l.slice(-200), {msg,tag,id:Date.now()+Math.random()}]);
    setTimeout(()=>logRef.current?.scrollTo(0,logRef.current.scrollHeight),20);
  },[]);

  const sleep = (ms) => new Promise(res=>{
    const check = ()=>{ if(stopRef.current) res(); else if(!pauseRef.current) res(); else setTimeout(check,100); };
    setTimeout(check, ms);
  });

  const simulate = async () => {
    if(!names.length){addLog("⚠  No names in list!","warn");return;}
    if(!steps.length){addLog("⚠  No steps in flow!","warn");return;}

    stopRef.current=false; pauseRef.current=false;
    setRunning(true); setPaused(false);
    setStats({success:0,fail:0,elapsed:0});
    const t0=Date.now();

    // Countdown
    for(let i=settings.countdown;i>0;i--){
      if(stopRef.current) break;
      setCountdown(i);
      addLog(`⏳ Starting in ${i}s…`,"dim");
      await sleep(1000);
    }
    setCountdown(0);
    if(stopRef.current){addLog("⛔ Stopped.","err");setRunning(false);return;}

    let success=0, failed=[];
    for(let i=0;i<names.length;i++){
      if(stopRef.current) break;
      while(pauseRef.current){await sleep(150);}
      if(stopRef.current) break;

      const name=names[i];
      setProgress({cur:i+1,total:names.length,name});
      addLog(`\n[${i+1}/${names.length}]  →  ${name}`,"head");

      let ok=true;
      for(const step of steps){
        if(stopRef.current||!ok) break;
        while(pauseRef.current){await sleep(150);}
        if(!step.enabled){addLog(`  ⊘ skip (disabled): ${STEP_TYPES[step.type]?.label}`,"dim");continue;}

        const summary=stepSummary({...step,text:step.text?.replace("{name}",name)});
        addLog(`  ▸ ${STEP_TYPES[step.type]?.icon} ${STEP_TYPES[step.type]?.label}  ${summary}`,"dim");

        if(step.type==="wait"){
          await sleep(step.seconds*1000);
        } else if(step.type==="loop"){
          for(let r=0;r<(step.times||2);r++){
            if(stopRef.current) break;
            addLog(`    ↺ Loop ${r+1}/${step.times}`,"dim");
            await sleep(200);
          }
        } else {
          await sleep(settings.stepDelay||80);
        }
      }

      if(ok){success++;setStats(s=>({...s,success:s.success+1}));addLog("  ✔  Done","ok");}
      else{failed.push(name);setStats(s=>({...s,fail:s.fail+1}));addLog("  ✘  Failed","err");}

      if(i<names.length-1&&!stopRef.current) await sleep(settings.between*1000);
    }

    const elapsed=(Date.now()-t0)/1000;
    setStats({success,fail:failed.length,elapsed:elapsed.toFixed(1)});
    addLog(`\n${"─".repeat(40)}`);
    addLog(`Done!  ✔ ${success} succeeded  ✘ ${failed.length} failed  ⏱ ${elapsed.toFixed(0)}s`,"ok");
    if(failed.length) addLog("Failed: "+failed.join(", "),"err");
    setRunning(false); setProgress({cur:0,total:0,name:""});
  };

  const stop = () => { stopRef.current=true; setPaused(false); pauseRef.current=false; };
  const togglePause = () => { pauseRef.current=!pauseRef.current; setPaused(p=>!p); addLog(pauseRef.current?"⏸ Paused":"▶ Resumed","warn"); };
  const clearLog = () => setLogs([]);

  const pct = progress.total ? Math.round(progress.cur/progress.total*100) : 0;

  return (
    <div>
      {/* Status row */}
      <div className="four-col" style={{marginBottom:16}}>
        <div className="stat-card"><div className="stat-value" style={{color:T.acc}}>{names.length}</div><div className="stat-label">Names</div></div>
        <div className="stat-card"><div className="stat-value" style={{color:T.purple}}>{steps.length}</div><div className="stat-label">Steps</div></div>
        <div className="stat-card"><div className="stat-value" style={{color:T.green}}>{stats.success}</div><div className="stat-label">Success</div></div>
        <div className="stat-card"><div className="stat-value" style={{color:T.red}}>{stats.fail}</div><div className="stat-label">Failed</div></div>
      </div>

      {/* Controls */}
      <div className="panel">
        <div style={{display:"flex",gap:10,flexWrap:"wrap",alignItems:"center"}}>
          {!running ? (
            <button className="btn btn-success" onClick={simulate} disabled={!names.length||!steps.length}>▶ Start Automation</button>
          ) : (
            <>
              <button className="btn btn-warning" onClick={togglePause}>{paused?"▶ Resume":"⏸ Pause"}</button>
              <button className="btn btn-danger" onClick={stop}>■ Stop</button>
            </>
          )}
          <button className="btn btn-ghost btn-sm" onClick={clearLog}>Clear Log</button>
          <button className="btn btn-ghost btn-sm" onClick={()=>{
            const blob=new Blob([logs.map(l=>l.msg).join("\n")],{type:"text/plain"});
            const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="swastik_log.txt";a.click();
          }}>⬇ Export Log</button>
          {countdown>0&&<span className="animate-pulse" style={{color:T.yellow,fontSize:14,fontWeight:700}}>Starting in {countdown}s…</span>}
          {running&&!paused&&!countdown&&<span className="animate-pulse" style={{color:T.red}}><span className="rec-dot" /> Running…</span>}
          {paused&&<span style={{color:T.yellow}}>⏸ Paused</span>}
        </div>

        {running&&progress.total>0&&(
          <div style={{marginTop:12}}>
            <div style={{display:"flex",justifyContent:"space-between",fontSize:11,color:T.fg3,marginBottom:4}}>
              <span>{progress.name}</span><span>{progress.cur} / {progress.total} ({pct}%)</span>
            </div>
            <div className="progress-bar"><div className="progress-fill" style={{width:`${pct}%`}} /></div>
          </div>
        )}
      </div>

      {/* Settings */}
      <div className="panel">
        <div className="panel-title">⚙ Run Settings</div>
        <div className="three-col">
          <div><label>Startup countdown (s)</label>
            <input type="number" min={0} value={settings.countdown} onChange={e=>setSettings(s=>({...s,countdown:+e.target.value}))} /></div>
          <div><label>Delay between names (s)</label>
            <input type="number" min={0} step="0.5" value={settings.between} onChange={e=>setSettings(s=>({...s,between:+e.target.value}))} /></div>
          <div><label>Retries on failure</label>
            <input type="number" min={0} value={settings.retries} onChange={e=>setSettings(s=>({...s,retries:+e.target.value}))} /></div>
        </div>
        <div style={{display:"flex",gap:20,marginTop:12}}>
          <label style={{display:"flex",gap:8,alignItems:"center",cursor:"pointer"}}>
            <Switch checked={settings.dryRun} onChange={v=>setSettings(s=>({...s,dryRun:v}))} />
            <span style={{fontSize:12,color:T.fg2}}>Practice mode (no real clicks)</span>
          </label>
          <label style={{display:"flex",gap:8,alignItems:"center",cursor:"pointer"}}>
            <Switch checked={settings.failSS} onChange={v=>setSettings(s=>({...s,failSS:v}))} />
            <span style={{fontSize:12,color:T.fg2}}>Screenshot on fail</span>
          </label>
        </div>
      </div>

      {/* Log */}
      <div className="panel">
        <div className="panel-title">Run Log</div>
        <div className="log-box" ref={logRef}>
          {logs.length===0&&<span style={{color:T.fg3}}>Log will appear here when you start…</span>}
          {logs.map(l=>(
            <div key={l.id} className={`log-line log-${l.tag||""}`}>{l.msg}</div>
          ))}
        </div>
      </div>
    </div>
  );
};

// ── Presets / Save-Load ───────────────────────────────────────────────────────
const PresetsTab = ({steps, names, settings, vars, onLoad}) => {
  const [presets, setPresets] = useState(()=>{
    try { return JSON.parse(localStorage.getItem("swastik_presets")||"[]"); }
    catch{ return []; }
  });
  const [saveName, setSaveName] = useState("");
  const [showJson, setShowJson] = useState(null);

  const save = () => {
    if(!saveName.trim()) return;
    const preset = { id: Date.now(), name: saveName.trim(), savedAt: new Date().toISOString(), steps, names, settings, vars };
    const updated=[preset,...presets.slice(0,19)];
    setPresets(updated);
    localStorage.setItem("swastik_presets", JSON.stringify(updated));
    setSaveName("");
  };

  const del = (id) => {
    const updated=presets.filter(p=>p.id!==id);
    setPresets(updated);
    localStorage.setItem("swastik_presets", JSON.stringify(updated));
  };

  const exportJson = (p) => {
    const blob=new Blob([JSON.stringify(p,null,2)],{type:"application/json"});
    const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=`${p.name}.json`;a.click();
  };

  const importJson = () => {
    const inp=document.createElement("input");inp.type="file";inp.accept=".json";
    inp.onchange=async(e)=>{
      try{const text=await e.target.files[0].text();const p=JSON.parse(text);onLoad(p);}
      catch{alert("Invalid JSON file");}
    };inp.click();
  };

  return (
    <div>
      <div className="two-col">
        <div className="panel">
          <div className="panel-title">💾 Save Current Flow</div>
          <div style={{display:"flex",gap:8}}>
            <input value={saveName} onChange={e=>setSaveName(e.target.value)} placeholder="Preset name…" onKeyDown={e=>e.key==="Enter"&&save()} />
            <button className="btn btn-primary btn-sm" onClick={save} disabled={!saveName.trim()}>Save</button>
          </div>
          <div style={{fontSize:11,color:T.fg3,marginTop:8}}>Saves: {steps.length} steps, {names.length} names, settings</div>
        </div>
        <div className="panel">
          <div className="panel-title">📂 Import / Export</div>
          <div style={{display:"flex",flexDirection:"column",gap:8}}>
            <button className="btn btn-ghost" onClick={importJson}>📥 Import JSON file</button>
            <button className="btn btn-ghost" onClick={()=>exportJson({name:"export",steps,names,settings,vars,savedAt:new Date().toISOString()})}>📤 Export current flow</button>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Saved Presets ({presets.length})</div>
        {presets.length===0&&<p style={{color:T.fg3,fontSize:12}}>No presets saved yet.</p>}
        {presets.map(p=>(
          <div key={p.id} style={{display:"flex",alignItems:"center",gap:10,padding:"10px 12px",background:T.bg3,borderRadius:8,marginBottom:6,border:`1px solid ${T.border}`}}>
            <div style={{flex:1}}>
              <div style={{fontSize:13,fontWeight:600,color:T.fg}}>{p.name}</div>
              <div style={{fontSize:10,color:T.fg3}}>{new Date(p.savedAt).toLocaleString()} · {(p.steps||[]).length} steps · {(p.names||[]).length} names</div>
            </div>
            <button className="btn btn-primary btn-xs" onClick={()=>onLoad(p)}>Load</button>
            <button className="btn btn-ghost btn-xs" onClick={()=>setShowJson(p)}>JSON</button>
            <button className="btn btn-ghost btn-xs" onClick={()=>exportJson(p)}>⬇</button>
            <button className="btn btn-ghost btn-xs" style={{color:T.red}} onClick={()=>del(p.id)}>✕</button>
          </div>
        ))}
      </div>

      {showJson&&(
        <Modal title={`JSON: ${showJson.name}`} onClose={()=>setShowJson(null)}>
          <div className="code-block">{JSON.stringify(showJson,null,2)}</div>
          <div style={{marginTop:8}}>
            <button className="btn btn-ghost btn-sm" onClick={()=>{navigator.clipboard.writeText(JSON.stringify(showJson,null,2));}}>Copy JSON</button>
          </div>
        </Modal>
      )}
    </div>
  );
};

// ── Scheduler Tab ─────────────────────────────────────────────────────────────
const SchedulerTab = ({schedules, setSchedules, steps, names}) => {
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({label:"", type:"once", time:"09:00", days:[], repeat:"daily"});
  const DAYS=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];

  const add = () => {
    if(!form.label.trim()) return;
    setSchedules(s=>[...s,{...form,id:Date.now(),active:true}]);
    setShowAdd(false);
  };
  const toggle = (id) => setSchedules(s=>s.map(sc=>sc.id===id?{...sc,active:!sc.active}:sc));
  const del = (id) => setSchedules(s=>s.filter(sc=>sc.id!==id));

  return (
    <div>
      <div className="panel">
        <div className="section-header">
          <span className="panel-title" style={{margin:0}}>⏰ Scheduled Runs</span>
          <button className="btn btn-primary btn-sm" onClick={()=>setShowAdd(true)}>＋ Add Schedule</button>
        </div>
        {schedules.length===0&&<p style={{color:T.fg3,fontSize:12}}>No schedules yet. Add one to auto-run your flow.</p>}
        {schedules.map(sc=>(
          <div key={sc.id} style={{display:"flex",alignItems:"center",gap:10,padding:"10px 14px",background:T.bg3,borderRadius:8,marginBottom:6,border:`1px solid ${sc.active?T.border:T.fg3}`,opacity:sc.active?1:0.6}}>
            <div style={{flex:1}}>
              <div style={{fontSize:13,fontWeight:600,color:T.fg}}>{sc.label}</div>
              <div style={{fontSize:11,color:T.fg3}}>
                {sc.type==="once"?"One-time":sc.repeat} at {sc.time}
                {sc.days?.length>0&&" · "+sc.days.join(", ")}
              </div>
            </div>
            <Switch checked={sc.active} onChange={()=>toggle(sc.id)} />
            <button className="btn btn-ghost btn-xs" style={{color:T.red}} onClick={()=>del(sc.id)}>✕</button>
          </div>
        ))}
      </div>
      <div className="panel" style={{background:T.bg3}}>
        <div style={{fontSize:12,color:T.fg2,lineHeight:1.8}}>
          <b style={{color:T.fg}}>📌 Note:</b><br/>
          Schedules are stored in the browser and managed by the web UI.<br/>
          To actually execute at the scheduled time, the desktop app (Python) must be running.<br/>
          Export your presets and use the desktop run.bat for true background scheduling.
        </div>
      </div>
      {showAdd&&(
        <Modal title="Add Schedule" onClose={()=>setShowAdd(false)}
          footer={<><button className="btn btn-ghost" onClick={()=>setShowAdd(false)}>Cancel</button><button className="btn btn-primary" onClick={add}>Add Schedule</button></>}>
          <div style={{display:"flex",flexDirection:"column",gap:12}}>
            <div><label>Label</label><input value={form.label} onChange={e=>setForm(f=>({...f,label:e.target.value}))} placeholder="e.g. Daily WhatsApp batch" /></div>
            <div><label>Time</label><input type="time" value={form.time} onChange={e=>setForm(f=>({...f,time:e.target.value}))} /></div>
            <div><label>Type</label><select value={form.type} onChange={e=>setForm(f=>({...f,type:e.target.value}))}>
              <option value="once">One-time</option><option value="repeat">Recurring</option></select></div>
            {form.type==="repeat"&&<div><label>Repeat</label><select value={form.repeat} onChange={e=>setForm(f=>({...f,repeat:e.target.value}))}>
              <option value="daily">Daily</option><option value="weekdays">Weekdays</option><option value="weekly">Weekly</option></select></div>}
            {form.type==="repeat"&&form.repeat==="weekly"&&(
              <div><label>Days</label><div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
                {DAYS.map(d=><button key={d} className={`tag${form.days.includes(d)?" active":""}`}
                  onClick={()=>setForm(f=>({...f,days:f.days.includes(d)?f.days.filter(x=>x!==d):[...f.days,d]}))}>
                  {d}</button>)}
              </div></div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
};

// ── Analytics Tab ─────────────────────────────────────────────────────────────
const AnalyticsTab = ({runHistory}) => {
  const total = runHistory.reduce((a,r)=>a+r.total,0);
  const success = runHistory.reduce((a,r)=>a+r.success,0);
  const rate = total>0?Math.round(success/total*100):0;
  const avgTime = runHistory.length>0?(runHistory.reduce((a,r)=>a+r.elapsed,0)/runHistory.length).toFixed(1):"—";

  return (
    <div>
      <div className="four-col" style={{marginBottom:16}}>
        <div className="stat-card"><div className="stat-value" style={{color:T.acc}}>{runHistory.length}</div><div className="stat-label">Total Runs</div></div>
        <div className="stat-card"><div className="stat-value" style={{color:T.green}}>{success}</div><div className="stat-label">Names Succeeded</div></div>
        <div className="stat-card"><div className="stat-value" style={{color:T.yellow}}>{rate}%</div><div className="stat-label">Success Rate</div></div>
        <div className="stat-card"><div className="stat-value" style={{color:T.purple}}>{avgTime}s</div><div className="stat-label">Avg Duration</div></div>
      </div>
      <div className="panel">
        <div className="panel-title">Run History</div>
        {runHistory.length===0?<p style={{color:T.fg3,fontSize:12}}>No runs yet.</p>:runHistory.slice().reverse().map((r,i)=>(
          <div key={i} style={{display:"flex",alignItems:"center",gap:12,padding:"8px 0",borderBottom:`1px solid ${T.border}`}}>
            <span style={{fontSize:10,color:T.fg3,minWidth:130,fontFamily:"'Fira Code',monospace"}}>{r.date}</span>
            <span style={{fontSize:12,color:T.fg,flex:1}}>{r.names} names · {r.steps} steps</span>
            <span style={{color:T.green,fontSize:11}}>✔ {r.success}</span>
            <span style={{color:T.red,fontSize:11}}>✘ {r.total-r.success}</span>
            <span style={{color:T.fg3,fontSize:11}}>⏱ {r.elapsed}s</span>
          </div>
        ))}
      </div>
    </div>
  );
};

// ── Settings Tab ─────────────────────────────────────────────────────────────
const SettingsTab = () => {
  const [shortcuts] = useState({save:"Ctrl+S",load:"Ctrl+O",undo:"Ctrl+Z",redo:"Ctrl+Y",stop:"F10",pause:"F11"});
  return (
    <div>
      <div className="panel">
        <div className="settings-section-title">⌨ Keyboard Shortcuts</div>
        <div className="two-col">
          {Object.entries(shortcuts).map(([k,v])=>(
            <div key={k} className="var-row">
              <span style={{fontSize:12,color:T.fg2,minWidth:120}}>{k.replace(/_/g," ").replace(/^\w/,c=>c.toUpperCase())}</span>
              <code style={{background:T.bg4,color:T.cyan,padding:"2px 8px",borderRadius:4,fontSize:11,border:`1px solid ${T.border}`}}>{v}</code>
            </div>
          ))}
        </div>
      </div>
      <div className="panel">
        <div className="settings-section-title">🌐 About Swastik RPA Web</div>
        <div style={{fontSize:12,color:T.fg2,lineHeight:1.8}}>
          <b style={{color:T.fg}}>Swastik RPA v9.2</b> — Web-based flow builder<br/>
          This web app is the <b>flow builder + simulator</b> frontend.<br/>
          For real automation (actual mouse clicks), use the Python desktop app with <code style={{color:T.cyan}}>python main.py</code>.<br/><br/>
          <b style={{color:T.fg}}>Workflow:</b><br/>
          1. Build your flow here → Export JSON<br/>
          2. Load JSON in the desktop app (📂 Load Flow)<br/>
          3. Run with real automation!
        </div>
      </div>
      <div className="panel">
        <div className="settings-section-title">📦 Install Desktop App</div>
        <div className="code-block">{`pip install pyautogui pyperclip pandas openpyxl Pillow pynput

# Optional — Vision Agent
pip install ollama
ollama pull llava

# Run the app
python main.py`}</div>
      </div>
    </div>
  );
};

// ── Help Tab ─────────────────────────────────────────────────────────────────
const HelpTab = () => (
  <div>
    <div className="two-col">
      {[
        {title:"🚀 Getting Started",items:["Add names to Name List tab","Build your flow in Flow Builder","Hit ▶ Start Automation in Run tab","Watch the log for results"]},
        {title:"🔑 Key Concepts",items:["{name} auto-replaced per record","Disable steps with 👁 icon","Drag ⠿ handle to reorder","Undo/Redo with Ctrl+Z/Y"]},
        {title:"💡 Pro Tips",items:["Always add Wait after clicks","Use Clear Field before typing","Clip Type for Unicode/Nepali","Practice mode = test safely"]},
        {title:"🖥 Desktop App",items:["Download Python code below","pip install dependencies","Load exported JSON flows","Real clicks, not simulation"]},
      ].map(s=>(
        <div key={s.title} className="panel">
          <div className="panel-title">{s.title}</div>
          <ul style={{paddingLeft:18,lineHeight:2,fontSize:12,color:T.fg2}}>
            {s.items.map((i,k)=><li key={k}>{i}</li>)}
          </ul>
        </div>
      ))}
    </div>
    <div className="panel">
      <div className="panel-title">📋 Step Reference</div>
      <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(200px,1fr))",gap:8}}>
        {Object.entries(STEP_TYPES).map(([type,info])=>(
          <div key={type} style={{display:"flex",alignItems:"center",gap:8,padding:"6px 10px",background:T.bg3,borderRadius:6,border:`1px solid ${T.border}`}}>
            <span style={{fontSize:16}}>{info.icon}</span>
            <div>
              <div style={{fontSize:11,fontWeight:600,color:info.color}}>{info.label}</div>
              <div style={{fontSize:10,color:T.fg3,fontFamily:"'Fira Code',monospace"}}>{type}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  </div>
);

// ── Main App ──────────────────────────────────────────────────────────────────
const TABS = [
  {id:"flow",    label:"Flow Builder", icon:"⚙"},
  {id:"names",   label:"Name List",    icon:"👥"},
  {id:"vars",    label:"Variables",    icon:"⟨⟩"},
  {id:"run",     label:"Run",          icon:"▶"},
  {id:"presets", label:"Presets",      icon:"💾"},
  {id:"schedule",label:"Schedule",     icon:"⏰"},
  {id:"analytics",label:"Analytics",  icon:"📊"},
  {id:"settings",label:"Settings",    icon:"⚙"},
  {id:"help",    label:"Help",         icon:"❓"},
];

export default function App() {
  const [tab, setTab] = useState("flow");
  const [flow, dispatch] = useReducer(flowReducer, {steps:[],history:[],future:[]});
  const [names, setNames] = useState(["Ram Bahadur","Sita Devi","Arjun Shah"]);
  const [vars, setVars] = useState({});
  const [settings, setSettings] = useState({countdown:5,between:1,retries:0,dryRun:false,failSS:false,stepDelay:80});
  const [schedules, setSchedules] = useState([]);
  const [runHistory] = useState([
    {date:"2026-04-21 14:23",names:5,steps:12,success:4,total:5,elapsed:47},
    {date:"2026-04-20 09:10",names:3,steps:8,success:3,total:3,elapsed:22},
  ]);

  // Keyboard shortcuts
  useEffect(()=>{
    const h=(e)=>{
      if((e.ctrlKey||e.metaKey)&&e.key==="z"){e.preventDefault();dispatch({type:"UNDO"});}
      if((e.ctrlKey||e.metaKey)&&e.key==="y"){e.preventDefault();dispatch({type:"REDO"});}
    };
    window.addEventListener("keydown",h);
    return()=>window.removeEventListener("keydown",h);
  },[]);

  const onLoadPreset = (p) => {
    if(p.steps) dispatch({type:"LOAD",steps:p.steps});
    if(p.names) setNames(p.names);
    if(p.vars)  setVars(p.vars);
    if(p.settings) setSettings(s=>({...s,...p.settings}));
    setTab("flow");
  };

  return (
    <>
      <style>{CSS}</style>
      <div className="rpa-root">
        {/* Sidebar */}
        <div className="sidebar">
          <div className="sidebar-logo">
            <h1>⚡ Swastik RPA</h1>
            <span>v9.2 Web Edition</span>
          </div>
          {TABS.map(t=>(
            <div key={t.id} className={`nav-item${tab===t.id?" active":""}`} onClick={()=>setTab(t.id)}>
              <span className="icon">{t.icon}</span>
              <span>{t.label}</span>
              {t.id==="names"&&<span className="badge" style={{background:T.bg4,color:T.fg3,marginLeft:"auto"}}>{names.length}</span>}
              {t.id==="flow"&&<span className="badge" style={{background:T.bg4,color:T.fg3,marginLeft:"auto"}}>{flow.steps.length}</span>}
            </div>
          ))}
          <div style={{marginTop:"auto",padding:"16px 20px",borderTop:`1px solid ${T.border}`}}>
            <div style={{fontSize:10,color:T.fg3,lineHeight:1.6}}>
              <span style={{color:T.green}}>●</span> Web Builder<br/>
              Export → load in desktop
            </div>
          </div>
        </div>

        {/* Main */}
        <div className="main">
          <div className="topbar">
            <span className="topbar-title">{TABS.find(t=>t.id===tab)?.icon} {TABS.find(t=>t.id===tab)?.label}</span>
            <button className="btn btn-ghost btn-sm" onClick={()=>{
              const data={steps:flow.steps,names,vars,settings,savedAt:new Date().toISOString()};
              const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});
              const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="swastik_flow.json";a.click();
            }}>📤 Export JSON</button>
            <button className="btn btn-ghost btn-sm" onClick={()=>{
              const inp=document.createElement("input");inp.type="file";inp.accept=".json";
              inp.onchange=async(e)=>{try{const t=await e.target.files[0].text();onLoadPreset(JSON.parse(t));}catch{alert("Invalid file");}};inp.click();
            }}>📥 Import JSON</button>
            <div style={{width:1,height:20,background:T.border}} />
            <Tip text="Undo (Ctrl+Z)"><button className="btn btn-ghost btn-sm" onClick={()=>dispatch({type:"UNDO"})} disabled={!flow.history.length}>↩</button></Tip>
            <Tip text="Redo (Ctrl+Y)"><button className="btn btn-ghost btn-sm" onClick={()=>dispatch({type:"REDO"})} disabled={!flow.future.length}>↪</button></Tip>
          </div>

          <div className="content">
            {tab==="flow"      && <FlowPanel state={flow} dispatch={dispatch} label="Main Flow" />}
            {tab==="names"     && <NameListTab names={names} setNames={setNames} />}
            {tab==="vars"      && <VariablesPanel vars={vars} setVars={setVars} />}
            {tab==="run"       && <RunTab names={names} steps={flow.steps} vars={vars} settings={settings} setSettings={setSettings} />}
            {tab==="presets"   && <PresetsTab steps={flow.steps} names={names} settings={settings} vars={vars} onLoad={onLoadPreset} />}
            {tab==="schedule"  && <SchedulerTab schedules={schedules} setSchedules={setSchedules} steps={flow.steps} names={names} />}
            {tab==="analytics" && <AnalyticsTab runHistory={runHistory} />}
            {tab==="settings"  && <SettingsTab />}
            {tab==="help"      && <HelpTab />}
          </div>
        </div>
      </div>
    </>
  );
}
