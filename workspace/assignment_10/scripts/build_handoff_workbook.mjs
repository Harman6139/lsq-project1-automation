import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const qa=path.resolve(root,'../../.qa_assignment10');
const require=createRequire(path.join(qa,'runtime/package.json'));
const {Workbook,SpreadsheetFile}=await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
await fs.mkdir(qa,{recursive:true});
const wb=Workbook.create();
if(process.argv.includes('--help-chart')){
 console.log(wb.help('chart series scatter source formulas',{search:'series|scatter|categoryFormula',include:'index,examples,notes',maxChars:6500}).ndjson);
 process.exit(0);
}
const font='Times New Roman', black='#000000';
const summary=JSON.parse(await fs.readFile(path.join(root,'data/results_summary.json'),'utf8'));
const design=JSON.parse(await fs.readFile(path.join(root,'data/frozen_design.json'),'utf8'));
const parseCSV=text=>{
 const rows=[];let row=[],field='',quoted=false;
 for(let i=0;i<text.length;i++){
  const c=text[i];
  if(c==='"'){if(quoted&&text[i+1]==='"'){field+='"';i++;}else quoted=!quoted;}
  else if(c===','&&!quoted){row.push(field);field='';}
  else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(field);if(row.some(v=>v!==''))rows.push(row);row=[];field='';}
  else field+=c;
 }
 if(field!==''||row.length){row.push(field);rows.push(row);}
 const [keys,...values]=rows;
 return values.map(r=>Object.fromEntries(keys.map((k,i)=>{const v=r[i]??'';return[k,v===''?null:v==='True'?true:v==='False'?false:Number.isFinite(Number(v))?Number(v):v];})));
};
async function csv(file,small=false){
 const text=await fs.readFile(path.join(root,'tables',file),'utf8');
 if(!small)return parseCSV(text);
 const imported=await Workbook.fromCSV(text,{sheetName:'CSV'});
 const [keys,...rows]=imported.worksheets.getItemAt(0).getUsedRange().values;
 return rows.filter(r=>r[0]!==null&&r[0]!=='').map(r=>Object.fromEntries(keys.map((k,i)=>{const v=r[i];return[k,v===null||v===''?null:Number.isFinite(Number(v))?Number(v):v];})));
}
const [comparison,naive,quantity,curves,external,support,folds]=await Promise.all([
 csv('handoff_comparison.csv',true),csv('naive_results.csv',true),csv('quantity_comparison.csv',true),
 csv('frontier_curves_original.csv'),csv('external_rates.csv'),csv('external_support.csv'),csv('strategy_fold_rates.csv')]);
if(comparison.length!==6||naive.length!==3||quantity.length!==42||design.policies.length!==38)throw Error('Incomplete handoff inputs');
const sheets=Object.fromEntries(['Comparison','Frontiers','Other histories','Sources'].map(n=>[n,wb.worksheets.add(n)]));
const maps={},formulaChecks=[];
const col=n=>{let s='';for(;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;};
function base(s,lastCol,lastRow){s.showGridLines=false;s.getRange(`A1:${col(lastCol)}${lastRow}`).format={font:{name:font,size:11,color:black},rowHeight:23,columnWidth:15,verticalAlignment:'center'};}
function widths(s,last,spec){for(const [c,w]of Object.entries(spec))s.getRange(`${c}1:${c}${last}`).format.columnWidth=w;}
function title(s,t){s.getRange('A2').values=[[t]];s.getRange('A2').format={font:{name:font,size:16,bold:true,color:black},rowHeight:31};}
function note(s,r,t,h=29){s.getRange(`A${r}`).values=[[t]];s.getRange(`A${r}`).format={rowHeight:h,font:{name:font,size:11,color:black}};}
function section(s,r,t){s.getRange(`A${r}`).values=[[t]];s.getRange(`A${r}`).format={font:{name:font,size:12,bold:true,color:black},rowHeight:29};}
function table(s,r,headers,values,key){
 const end=col(headers.length);s.getRange(`A${r}:${end}${r}`).values=[headers];
 s.getRange(`A${r}:${end}${r}`).format={fill:'#E7E6E6',font:{name:font,size:11,bold:true,color:black},rowHeight:43,wrapText:true,horizontalAlignment:'center',borders:{bottom:{style:'thin',color:black}}};
 if(values.length)s.getRange(`A${r+1}:${end}${r+values.length}`).values=values;
 maps[key]={sheet:s.name,header:r,start:r+1,end:r+values.length,columns:headers,values};return r+values.length;
}
function rates(s,column,start,end,denom,numerator){
 s.getRange(`${column}${start}:${column}${end}`).formulas=Array.from({length:end-start+1},(_,i)=>[`=${numerator}${start+i}/${denom}${start+i}`]);
 s.getRange(`${column}${start}:${column}${end}`).setNumberFormat('0.0%');
}
function fmt(s,cs,start,end,f){for(const c of cs)s.getRange(`${c}${start}:${c}${end}`).setNumberFormat(f);}
const mechanism={unmodified:'Unchanged',relative_permanent:'Small losses removed',relative_delay3:'Small losses delayed 3 months',fixed_delay3:'Losses below 1% delayed 3 months',relative_half_delay3:'Half of small losses delayed 3 months',smooth25:'25% adjacent-month averaging',smooth50:'50% adjacent-month averaging',smooth75:'75% adjacent-month averaging'};
const policy={B:'Bias ratio (B)',D:'Normal loss count (D)',A:'Serial dependence (A)',Z:'Local zero bins (Z)','OR:B+D':'Original pair: B + D','OR:A+Z':'Local + serial: A + Z','OR:B+A+Z':'Three checks: B + A + Z','OR:B+D+A+Z':'All four checks'};
const policyName=x=>policy[x]??x;
const month=x=>Math.round((Date.UTC(Number(String(x).slice(0,4)),Number(String(x).slice(5,7))-1,1)-Date.UTC(1899,11,30))/86400000);

const c=sheets.Comparison;base(c,11,105);title(c,'Return screening: what improves the comparison?');
note(c,4,'The original rules rarely flag unchanged strategies. Raising their cutoff also hides more imposed loss delays.');
note(c,5,'The earlier descriptive panel had 1 alert in 195 strategies. All calibrated US comparisons below use the same 194 complete histories.');
section(c,6,'Starting point: losses up to 1%, recognised three months later');
table(c,7,['Cutoff approach','Strategies','Unchanged flags','Unchanged rate','Altered flags','Altered rate','New flags','New rate'],naive.map(r=>[r.approach,r.n,r.unchanged_warnings,null,r.altered_warnings,null,r.new_warnings,null]),'starting_point');
rates(c,'D',8,10,'B','C');rates(c,'F',8,10,'B','E');rates(c,'H',8,10,'B','G');
section(c,13,'Change the kind of screen, keeping the old 5% reference budget');
table(c,14,['Return histories','Reporting change','Strategies','Original pair flags','Original pair rate','Local + serial flags','Local + serial rate','Original unchanged flags','Local + serial unchanged flags','Original new flags','Local + serial new flags'],comparison.map(r=>[r.source,r.case,r.n,r.old_pair_warnings,null,r.local_serial_pair_warnings,null,r.old_pair_baseline,r.local_serial_pair_baseline,r.old_pair_new,r.local_serial_pair_new]),'main_comparison');
rates(c,'E',15,20,'C','D');rates(c,'G',15,20,'C','F');
c.getRange('A15:B20').format.wrapText=true;c.getRange('A15:K20').format.rowHeight=42;
note(c,22,'The 5% budget refers to older reference histories. Actual later warning rates differ and are shown above.');
note(c,23,'An alert is a reason to investigate. Unchanged backtests are not verified honest funds, and imposed changes are not fraud labels.');
section(c,26,'How many checks? Choose on older data, then evaluate on 2017–2025 returns');
const quantityRows=quantity.filter(r=>[1,2,3,4].includes(Number(r.scope))).sort((a,b)=>Number(a.scope)-Number(b.scope)||Object.keys(mechanism).indexOf(a.mechanism)-Object.keys(mechanism).indexOf(b.mechanism));
table(c,27,['Number of checks','Selected rule','Reporting change','Strategies','Unchanged flags','Unchanged rate','Altered flags','Altered rate','New flags','New rate'],quantityRows.map(r=>[Number(r.scope),policyName(r.policy),mechanism[r.mechanism]??r.mechanism,r.n,r.baseline,null,r.altered,null,r.new,null]),'number_of_checks');
rates(c,'F',28,55,'D','E');rates(c,'H',28,55,'D','G');rates(c,'J',28,55,'D','I');
c.getRange('B28:C55').format.wrapText=true;c.getRange('A28:J55').format.rowHeight=35;
c.getRange('A28:A55').format.horizontalAlignment='center';
note(c,57,'The pair does most of the work on the later US panel. The exceptional early ML history below shows why a third check can still matter.');
section(c,60,'Five held-out strategy groups: pooled counts, with choices made without each group');
const foldRows=[];
for(const scope of ['1','2','3','4'])for(const mech of ['unmodified','relative_delay3','smooth50']){
 const rr=folds.filter(r=>String(r.scope)===scope&&r.budget===.05&&r.mechanism===mech);
 if(rr.length!==5)throw Error('Missing held-out strategy fold');
 foldRows.push([Number(scope),mechanism[mech],rr.reduce((a,r)=>a+r.n,0),rr.reduce((a,r)=>a+r.baseline,0),null,rr.reduce((a,r)=>a+r.altered,0),null]);
}
table(c,61,['Number of checks','Reporting change','Strategies','Unchanged flags','Unchanged rate','Altered flags','Altered rate'],foldRows,'heldout_groups');
rates(c,'E',62,73,'C','D');rates(c,'G',62,73,'C','F');c.getRange('B62:B73').format.wrapText=true;c.getRange('A62:G73').format.rowHeight=32;
c.getRange('A62:A73').format.horizontalAlignment='center';
note(c,75,'This checks transfer across strategies. The original and altered paths are paired; it does not identify dishonesty in a real fund.');
widths(c,105,{A:29,B:34,C:17,D:18,E:17,F:19,G:18,H:18,I:20,J:18,K:21});c.freezePanes.freezeRows(7);

const f=sheets.Frontiers;base(f,16,745);title(f,'Warning trade-offs on later US strategies');
note(f,4,'Horizontal axis: actual unchanged-record warning rate. Vertical axis: total altered-record warning rate.');
note(f,5,'Each point uses an older-data cutoff. Curves show 0–20% reference budgets, not equal actual investigation costs.');
const chosen=['B','D','A','Z','OR:B+D','OR:A+Z','OR:B+A+Z','OR:B+D+A+Z'];
const mechs=['relative_permanent','relative_delay3','fixed_delay3','smooth50'];
const frontier=curves.filter(r=>r.group==='all'&&r.budget<=.20&&mechs.includes(r.mechanism)&&chosen.includes(r.policy)).sort((a,b)=>mechs.indexOf(a.mechanism)-mechs.indexOf(b.mechanism)||chosen.indexOf(a.policy)-chosen.indexOf(b.policy)||a.budget-b.budget);
if(frontier.length!==672)throw Error('Frontier subset incomplete');
const frontierEnd=table(f,32,['Reporting change','Rule','Old reference budget','Strategies','Unchanged flags','Unchanged rate','Altered flags','Altered rate','New flags','Paths changed'],frontier.map(r=>[mechanism[r.mechanism],policyName(r.policy),r.budget,r.n,r.baseline,null,r.altered,null,r.new,r.changed]),'frontier_points');
rates(f,'F',33,frontierEnd,'D','E');rates(f,'H',33,frontierEnd,'D','G');fmt(f,['C'],33,frontierEnd,'0%');
f.getRange(`A33:B${frontierEnd}`).format.wrapText=true;f.getRange(`A33:J${frontierEnd}`).format.rowHeight=34;
widths(f,745,{A:34,B:29,C:17,D:13,E:17,F:18,G:17,H:18,I:15,J:16,K:3,L:12,M:12,N:12,O:12,P:12});f.freezePanes.freezeRows(5);
const figurePath=path.join(root,'figures/frontier_types_and_quantity.png');
const figureBytes=await fs.readFile(figurePath);
f.images.add({dataUrl:`data:image/png;base64,${figureBytes.toString('base64')}`,anchor:{from:{row:6,col:0},extent:{widthPx:1540,heightPx:613}}});
const figureHash=createHash('sha256').update(figureBytes).digest('hex');
note(f,28,'Dots mark the old 5% reference allowance. The selected one-, two-, three- and four-check specifications are fixed before later-data evaluation.');
note(f,29,'The figure highlights loss delays and averaging. The full table also includes permanent loss removal and the fixed 1% loss-delay sensitivity.');

const o=sheets['Other histories'];base(o,13,250);title(o,'Other return histories: performance and screening');
note(o,4,'Monthly Sharpe ratios use excess returns. Research portfolios are gross backtests; the three fund histories are published net USD NAVs.');
section(o,6,'Performance support and the high-Sharpe example');
const perf=[];
for(const sample of ['first108','second108','final108_overlap','published_test300']){
 const r=support.find(r=>r.source==='CPZ_author'&&r.sample===sample&&r.series==='SDF');
 if(!r)throw Error('Missing CPZ performance block');
 const ex=summary.exceptional_history.find(x=>x.sample===sample);
 perf.push(['Chen–Pelger–Zhu ML portfolio',month(r.start),month(r.end),r.months,1,r.mean,r.sd,r.excess_sharpe,ex.losing_months,ex.small_losses_eligible,'Gross author backtest']);
}
const world=support.filter(r=>r.source==='JKP_world');
const worldBest=world.reduce((a,b)=>a.excess_sharpe>b.excess_sharpe?a:b);
perf.push(['World factor portfolios: best of 153',month(worldBest.start),month(worldBest.end),108,153,worldBest.mean,worldBest.sd,worldBest.excess_sharpe,null,null,'Gross stock-strategy backtests']);
for(const r of support.filter(r=>r.source==='public_NAV'||r.source==='Fund_X'))perf.push([({BH_Macro_USD:'BH Macro USD',Parus_I_USD:'Parus I USD',Winton_Alma_I1C_U:'Winton Alma I1C USD'}[r.series]??'Fund X'),month(r.start),month(r.end),r.months,1,r.mean,r.sd,r.excess_sharpe,null,null,'Published net returns']);
table(o,7,['Return history','Start','End','Months','Series count','Monthly mean','Monthly SD','Monthly excess Sharpe','Losing months','Small losses eligible','Return basis'],perf,'performance_support');
fmt(o,['B','C'],8,7+perf.length,'mmm-yy');fmt(o,['F','G'],8,7+perf.length,'0.00%');fmt(o,['H'],8,7+perf.length,'0.000');
o.getRange(`A8:A${7+perf.length}`).format.wrapText=true;o.getRange(`A8:K${7+perf.length}`).format.rowHeight=37;
o.getRange(`K8:K${7+perf.length}`).format.wrapText=true;
note(o,19,'The 1992–2000 ML block is exceptional, but later performance weakened. Its 2008–2016 block overlaps the preceding block.');
section(o,22,'High-Sharpe ML history: 1992–2000, nine losses and four eligible small losses');
const ex=summary.exceptional_history.find(r=>r.sample==='first108');
table(o,23,['Rule','Unchanged alert','3-month loss-delay alert','50% averaging alert'],[
 [policyName('OR:B+D'),ex.old_pair_original,ex.old_pair_delay3,ex.old_pair_smoothed],
 [policyName('OR:A+Z'),ex.local_serial_pair_original,ex.local_serial_pair_delay3,ex.local_serial_pair_smoothed],
 [policyName('OR:B+A+Z'),ex.three_rules_original,ex.three_rules_delay3,ex.three_rules_smoothed]
],'exceptional_case');
note(o,28,'The local + serial pair misses this loss delay; adding the bias ratio catches it. This pair is not universally best.');
note(o,29,'For the ML histories, development ends in 1979 and the reference period is 1980–1991. No later returns set these cutoffs.');
section(o,32,'Selected rules at the 5% historical reference budget');
const externalPolicies=['OR:B+D','OR:A+Z','OR:B+A+Z','OR:B+D+A+Z'];
const externalMechs=['unmodified','relative_permanent','relative_delay3','relative_half_delay3','smooth50'];
const selectedExternal=external.filter(r=>r.budget===.05&&externalPolicies.includes(r.policy)&&externalMechs.includes(r.mechanism)&&(
 (r.source==='CPZ_author'&&r.group==='SDF')||(r.source==='JKP_world'&&r.group==='all')||
 (r.source==='public_NAV'&&r.group!=='all')||(r.source==='Fund_X'&&r.group==='case_only')))
 .sort((a,b)=>`${a.source}|${a.sample}|${a.group}|${a.policy}`.localeCompare(`${b.source}|${b.sample}|${b.group}|${b.policy}`)||externalMechs.indexOf(a.mechanism)-externalMechs.indexOf(b.mechanism));
const extEnd=table(o,33,['Return history','Sample','Reporting change','Rule','Records','Paths changed','Unchanged flags','Unchanged rate','Altered flags','Altered rate','New flags','New rate'],selectedExternal.map(r=>[r.source==='public_NAV'?({BH_Macro_USD:'BH Macro USD',Parus_I_USD:'Parus I USD',Winton_Alma_I1C_U:'Winton Alma I1C USD'}[r.group]):r.source==='CPZ_author'?'CPZ ML portfolio':r.source==='JKP_world'?'World factor portfolios':'Fund X',`${r.start} to ${r.end}`,mechanism[r.mechanism]??r.mechanism,policyName(r.policy),r.n,r.changed,r.baseline,null,r.altered,null,r.new,null]),'external_results');
rates(o,'H',34,extEnd,'E','G');rates(o,'J',34,extEnd,'E','I');rates(o,'L',34,extEnd,'E','K');
o.getRange(`A34:D${extEnd}`).format.wrapText=true;o.getRange(`A34:L${extEnd}`).format.rowHeight=37;
note(o,extEnd+2,'Zero changed paths means that the mechanism had no eligible losses. Such rows remain shown; their alerts can predate the imposed change.');
note(o,extEnd+3,'Fund X is shown unchanged only. Imposed reporting changes are applied to the comparator histories.');
widths(o,extEnd+5,{A:35,B:24,C:35,D:29,E:13,F:16,G:17,H:18,I:16,J:17,K:30,L:16,M:3});o.freezePanes.freezeRows(7);

const s=sheets.Sources;base(s,6,135);title(s,'Definitions, design and sources');
table(s,5,['Item','Definition'],[
 ['Purpose','Compare the kind and number of return checks, including their warning burden and their coverage of specified reporting changes.'],
 ['Warning burden','Fraction of unchanged histories flagged. Without verified reporting labels, this is not a measured false-fraud rate.'],
 ['Altered warning rate','All altered histories flagged / all histories. New warning rate counts only records newly flagged after the change.'],
 ['Paired changes','Keep the underlying path fixed. Small losses lie between minus 0.25 baseline monthly SD and zero, replaced by plus 0.0125 SD.'],
 ['Temporary delay','The entire hidden amount is returned after the stated lag. The permanent version does not restore it within the sample.'],
 ['Averaging','A causal filter combines the current and previous monthly return. The 50% case weights each equally.'],
 ['Main phases','Development: 1980–2004. Reference calibration: 2005–2016. Evaluation: January 2017–December 2025, 108 months and 194 complete strategies.'],
 ['Historical budget','A cutoff calibrated on older resampled histories. A 5% historical budget does not fix the actual warning rate in later data.'],
 ['Joint calibration','Each combined rule has its own cutoff. Combining two separate 5% rules would generally spend a different warning budget.'],
 ['Selection','Choose using older calibration histories only, by mean newly flagged fraction across declared mechanisms; ties prefer fewer checks, then alphabetical rule ID.'],
 ['Ranks','Each primitive score is mapped to its fixed historical empirical rank. Strict exceedance is used, so ties do not become warnings.'],
 ['OR / MAJ / MEAN / PCA','OR uses the largest rank; MAJ uses the majority order statistic; MEAN averages ranks; PCA is the leading standardized rank component.'],
 ['Interpretation','These are controlled sensitivity comparisons, not estimates of real fraud detection. Reconstruction, survivorship and model choices limit generalization.'],
 ['Contribution','Existing research already combines return flags. The increment here is out-of-time comparison of specified reporting mechanisms and transparent transfer limits.'],
 ['ML source scale','CPZ monthly stock weights have gross notional one. US and world long–short factors have gross notional two. Relative-SD changes reduce scale confounding.'],
 ['Returns and costs','Factor and ML series are already excess payoffs, gross of costs. Net USD NAV returns are compared after subtracting the frozen monthly USD risk-free rate.'],
 ['Public fund coverage','BH Macro, Parus I USD and Winton Alma I1C USD cover 2017–2025, with actual July–December 2016 warm-up. They are three surviving histories.'],
 ['Monthly Sharpe','Mean monthly excess return divided by its sample SD; no annualization. It differs from mean total return / SD when cash rates are positive.'],
 ['Complete results','Full CSV results, frozen design, scripts and provenance are retained alongside this compact workbook.']
],'definitions');
s.getRange('B6:B24').format.wrapText=true;s.getRange('A6:B24').format.rowHeight=48;
section(s,27,'The four primitive checks');
table(s,28,['Code','Meaning'],[
 ['B','Bias ratio: count of returns in [0, SD], divided by one plus the count in [−SD, 0).'],
 ['D','Loss-count deficit against a fitted Gaussian distribution. This is the paper’s adaptation, not the original Bollen–Pool test.'],
 ['A','Positive first-order demeaned autocorrelation: whether adjacent monthly returns move together. It does not identify the cause.'],
 ['Z','Compare the excess of gains over losses in the nearest zero bins with that in the next bins; bin width is 0.25 SD. Exact zeros are separate.']
],'primitives');s.getRange('B29:B32').format.wrapText=true;s.getRange('A29:B32').format.rowHeight=45;
section(s,35,'The 38 declared candidate specifications');
table(s,36,['Rule ID','Inputs','Number of checks','Combination','Role'],design.policies.map(r=>[r.id,r.indices.map(i=>['B','D','A','Z'][i]).join(' + '),r.count,({any:'OR',majority:'Majority',mean:'Mean',pca:'Principal component'}[r.aggregation]??r.aggregation),r.primary?'Primary':'Secondary']), 'candidate_specs');
s.getRange('C37:C74').format.horizontalAlignment='center';
section(s,77,'Data releases');
table(s,78,['Source','Return history and release','URL'],[
 ['Chen–Zimmermann','Pinned official October 2026 release, reconstructed monthly US strategies ending December 2025.','https://www.openassetpricing.com/data/'],
 ['Chen–Pelger–Zhu','Author SDF Time-Series.xlsx; normalized factor excess returns, January 1967–December 2016. Test period: 1992–2016.','https://mpelger.people.stanford.edu/data-and-code'],
 ['Jensen–Kelly–Pedersen','World, all factors, monthly, capped-value weight; August 2026 public release ending December 2025.','https://jkpfactors.com/data'],
 ['BH Macro','January 2026 factsheet, published USD NAV return table.','https://bhmacro.com/wp-content/uploads/2026/03/BH-Macro-Factsheet-January-2026-ADV022631.pdf'],
 ['Parus','September 2026 factsheet, I USD monthly NAV returns.','https://www.almacapital.com/wp-content/uploads/2020/10/Factsheet_Parus_UCITS_2026-09.pdf'],
 ['Winton Alma','September 2026 factsheet, I1C U USD monthly NAV returns.','https://www.almacapital.com/wp-content/uploads/2019/10/Factsheet_Winton-Alma-Diversified-Macro-Fund_2026_09.pdf'],
 ['Fund X / cash rate','Fund X monthly source and French monthly RF frozen in Assignment 9, unchanged here.','https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html']
],'data_sources');s.getRange('B79:C85').format.wrapText=true;s.getRange('A79:C85').format.rowHeight=56;
section(s,88,'Closest published work and the actual distinction');
table(s,89,['Paper','What it already establishes','URL'],[
 ['Bollen & Pool (2012), RFS','Combines return warning signs and compares investigation costs. This study does not claim to invent combined screens or warning-budget comparisons.','https://doi.org/10.1093/rfs/hhs085'],
 ['Bollen & Pool (2009), JF','Studies discontinuities around zero in pooled hedge-fund returns. A fitted Gaussian count for one return history is a distinct adaptation.','https://doi.org/10.1111/j.1540-6261.2009.01500.x'],
 ['Bollen & Pool (2008), JFQA','Studies conditional return smoothing. The present imposed-delay and averaging cases do not constitute real misreporting labels.','https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/conditional-return-smoothing-in-the-hedge-fund-industry/242F5FBBC32FCA77BBDD1FB2F0F1FA94'],
 ['Getmansky, Lo & Makarov (2004), JFE','Shows that serial correlation can reflect illiquidity and smoothing. An autocorrelation flag does not establish dishonesty.','https://doi.org/10.1016/j.jfineco.2004.04.001'],
 ['Chen & Zimmermann (2022), CFR','Supplies the systematically reproduced stock-return predictors used here; these are strategy backtests, not additional hedge funds.','https://doi.org/10.1093/cfr/cfab023'],
 ['Chen, Pelger & Zhu (2024), Management Science','Provides the ML asset-pricing portfolio. Its exceptional early test segment and weaker later period are kept together here.','https://doi.org/10.1287/mnsc.2023.4695'],
 ['Jensen, Kelly & Pedersen (2023), JF','Provides internationally replicated factors. The world panel is outside the original source but shares economic factor constructions.','https://doi.org/10.1111/jofi.13249']
],'literature');s.getRange('B90:C96').format.wrapText=true;s.getRange('A90:C96').format.rowHeight=68;
s.getRange('A90:A96').format.wrapText=true;
widths(s,135,{A:38,B:100,C:78,D:25,E:18,F:3});s.freezePanes.freezeRows(5);

// A real count change must update the displayed rate, then be restored.
wb.recalculate();const originalCount=c.getRange('D15').values[0][0];
c.getRange('D15').values=[[originalCount+1]];wb.recalculate();
const perturbed=c.getRange('E15').values[0][0];
if(Math.abs(perturbed-(originalCount+1)/comparison[0].n)>1e-12)throw Error('Count perturbation did not recalculate');
c.getRange('D15').values=[[originalCount]];wb.recalculate();
if(Math.abs(c.getRange('E15').values[0][0]-originalCount/comparison[0].n)>1e-12)throw Error('Rate not restored');
formulaChecks.push({sheet:'Comparison',input:'D15',output:'E15',original_count:originalCount,perturbed_count:originalCount+1,denominator:comparison[0].n,perturbed_rate:perturbed,restored_rate:c.getRange('E15').values[0][0]});
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:100},summary:'Final formula-error scan'});
await fs.writeFile(path.join(qa,'workbook_formula_scan.json'),JSON.stringify(errors,null,2));
for(const key of Object.keys(maps)){
 const m=maps[key],sheet=sheets[m.sheet];m.saved_values=sheet.getRange(`A${m.start}:${col(m.columns.length)}${m.end}`).values;
 m.formulas=sheet.getRange(`A${m.start}:${col(m.columns.length)}${m.end}`).formulas;
}
await fs.writeFile(path.join(qa,'workbook_cell_map.json'),JSON.stringify(maps));
const renderRegions=[
 ['Comparison','A1:K24','comparison_main'],['Comparison','A26:J43','comparison_quantity'],['Comparison','A44:J57','comparison_quantity_tail'],['Comparison','A60:G76','comparison_folds'],
 ['Frontiers','A1:K30','frontiers_charts'],['Frontiers','A31:J44','frontiers_data'],['Frontiers',`A${frontierEnd-8}:J${frontierEnd}`,'frontiers_tail'],
 ['Other histories','A1:K30','other_performance'],['Other histories','A32:L48','other_screening'],['Other histories',`A${extEnd-9}:L${extEnd+3}`,'other_tail'],
 ['Sources','A1:B24','sources_definitions'],['Sources','A26:B33','sources_primitives'],['Sources','A35:E53','sources_candidates'],['Sources','A54:E74','sources_candidates_tail'],['Sources','A77:C86','sources_data'],['Sources','A88:C97','sources_literature']
];
const affectedOnly=process.argv.includes('--render-affected-wording');
for(const [sheetName,range,name]of renderRegions){if(affectedOnly&&!['comparison_main','other_performance'].includes(name))continue;const img=await wb.render({sheetName,range,scale:1,format:'png'});await fs.writeFile(path.join(qa,`${name}.png`),Buffer.from(await img.arrayBuffer()));}
const output=path.join(root,'Assignment_10_Return_Screening_Frontier_Handoff.xlsx');
const xlsx=await SpreadsheetFile.exportXlsx(wb);await xlsx.save(output);
try{await fs.rename(`${output}.inspect.ndjson`,path.join(qa,'workbook_export_inspect.ndjson'));}catch(e){if(e.code!=='ENOENT')throw e;}
const copydir=path.join(root,'outputs','assignment10_handoff_20261119');await fs.mkdir(copydir,{recursive:true});await fs.copyFile(output,path.join(copydir,path.basename(output)));
const hash=createHash('sha256').update(await fs.readFile(output)).digest('hex');
await fs.writeFile(path.join(qa,'workbook_build_checks.json'),JSON.stringify({output,sha256:hash,sheets:Object.keys(sheets),table_rows:Object.fromEntries(Object.entries(maps).map(([k,v])=>[k,v.values.length])),formulaChecks,figure:{path:figurePath,sha256:figureHash},renderRegions,authoring_event:{operation:'create',count:1,format:'xlsx',marker_script:'Not present in installed 26.1118.11504 package; this single local event records the authoring start.'}},null,2));
console.log(JSON.stringify({output,sha256:hash,tables:Object.fromEntries(Object.entries(maps).map(([k,v])=>[k,v.values.length])),renders:renderRegions.length}));
