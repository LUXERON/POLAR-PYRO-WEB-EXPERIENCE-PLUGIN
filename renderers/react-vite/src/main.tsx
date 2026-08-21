import React from "react";
import { createRoot } from "react-dom/client";
import plan from "./generated/ui-plan.json";
import capability from "./generated/capability.json";
import "./styles.css";

type RegionSpec={id:string;component_id:string;query_ids:string[];command_ids:string[]};
type RouteSpec={route_id:string;recipe_id:string;regions:RegionSpec[]};
type Named={id:string};
const typedCapability=capability as {commands:Named[];queries:Named[]};
const commands=new Map<string,Named>(typedCapability.commands.map(item=>[item.id,item]));
const queries=new Map<string,Named>(typedCapability.queries.map(item=>[item.id,item]));
const label=(value:string)=>value.replace(/[._-]+/g," ").replace(/\b\w/g,c=>c.toUpperCase());

function Region({region}:{region:RegionSpec}){
  return <section className="panel" data-component={region.component_id} data-testid={region.id} aria-labelledby={`${region.id}-title`}>
    <header><p className="eyebrow">{label(region.component_id)}</p><h2 id={`${region.id}-title`}>{label(region.id.split(".").at(-1)??region.id)}</h2></header>
    <div className="status-grid" aria-label="Content state demonstrations">
      {['loading','empty','ready','error','recovering','forbidden'].map(state=><span key={state} data-state={state}>{label(state)}</span>)}
    </div>
    {region.query_ids.length>0&&<div className="evidence"><h3>Available evidence</h3>{region.query_ids.map(id=><p key={id} data-query={id}>{label(queries.get(id)?.id??id)}</p>)}</div>}
    <div className="actions">{region.command_ids.map(id=><button type="button" key={id} data-command={id} onClick={()=>window.dispatchEvent(new CustomEvent("luxeron:command",{detail:{id}}))}>{label(commands.get(id)?.id??id)}</button>)}</div>
  </section>;
}
function App(){const routes=plan.routes as RouteSpec[];const [active,setActive]=React.useState(routes[0]?.route_id??"");const current=routes.find(item=>item.route_id===active);return <div className="shell"><aside><p className="brand">LUXERON</p><h1>{label(plan.application_id)}</h1><nav aria-label="Primary navigation">{routes.map(route=><button key={route.route_id} aria-current={active===route.route_id?"page":undefined} onClick={()=>setActive(route.route_id)}>{label(route.route_id)}</button>)}</nav></aside><main><header className="hero"><p className="eyebrow">Verified experience</p><h2>{label(current?.route_id??"Workspace")}</h2><p>Deterministically rendered from a proof-bound UI plan.</p></header>{current?.regions.map(region=><Region key={region.id} region={region}/>)}</main></div>}
createRoot(document.getElementById("root")!).render(<React.StrictMode><App/></React.StrictMode>);
