import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const qa=path.resolve(root,'../../.qa_assignment9');
const require=createRequire(path.join(qa,'runtime/package.json'));
const {Workbook,SpreadsheetFile}=await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const font='Times New Roman';
await fs.mkdir(qa,{recursive:true});
async function json(file){return JSON.parse(await fs.readFile(path.join(root,file),'utf8'));}
async function csv(file){
 const imported=await Workbook.fromCSV(await fs.readFile(path.join(root,file),'utf8'),{sheetName:'CSV'});
 const [keys,...rows]=imported.worksheets.getItemAt(0).getUsedRange().values;
 return rows.filter(row=>row[0]!==null&&row[0]!=='').map(row=>Object.fromEntries(keys.map((key,i)=>{
  const v=row[i];
  if(v===null||v==='')return [key,null];
  if(v==='True')return [key,true];if(v==='False')return [key,false];
  return [key,typeof v==='number'?v:(Number.isFinite(Number(v))?Number(v):String(v))];
 })));
}
const [design,cutoffs,provenance,descmeta,comboDesign,stats,quintiles,logit,observedOP,observedVW,
 calOP,calVW,bootOP,bootVW,reportPoint,reportSelected,reportBoot,reportSensitivity,smoothing,combinations]=await Promise.all([
 json('data/frozen_design.json'),json('data/locked_cutoffs.json'),json('data/source_provenance.json'),json('data/descriptive_metadata.json'),json('data/exploratory_combination_design.json'),
 csv('tables/descriptive_statistics.csv'),csv('tables/descriptive_quintiles.csv'),csv('tables/descriptive_logit.csv'),
 csv('tables/observed_selection_original.csv'),csv('tables/observed_selection_value_weighted.csv'),
 csv('tables/bootstrap_calibration_original.csv'),csv('tables/bootstrap_calibration_value_weighted.csv'),
 csv('tables/bootstrap_validation_original.csv'),csv('tables/bootstrap_validation_value_weighted.csv'),
 csv('tables/reporting_point.csv'),csv('tables/reporting_selection.csv'),csv('tables/reporting_bootstrap_ranges.csv'),
 csv('tables/reporting_sensitivity.csv'),csv('tables/smoothing_sensitivity.csv'),csv('tables/exploratory_combination_statistics.csv')]);
if(stats.length!==782||quintiles.length!==25||logit.length!==20||observedOP.length!==360||observedVW.length!==360||reportPoint.length!==960||reportSelected.length!==240||reportBoot.length!==80||reportSensitivity.length!==480||smoothing.length!==120||combinations.length!==12)throw Error('Expected result tables incomplete');
const weight=x=>({original:'Original-paper',value_weighted:'Forced value',fund_x:'Fund X'}[x]??x);
const series=x=>({spread:'Long-short spread',funded:'Cash + spread',reported_total_return:'Reported total return'}[x]??x);
const methods={conventional_bias:'Bias ratio > 2',conventional_normal:'Normal count p < 0.05',conventional_any:'Either conventional rule',ordinary_calibrated:'Ordinary-reference score',selection_calibrated:'Selection-reference score'};
const method=x=>methods[x]??x;
const rule=x=>({equal_notional:'Equal notional',inverse_calibration_volatility:'Inverse volatility',maximum_calibration_sharpe:'Capped maximum Sharpe'}[x]??String(x).replaceAll('_',' '));
const recognition=x=>String(x)==='permanent'?'Permanent':`${x} month${String(x)==='1'?'':'s'}`;
const yes=x=>x?'Yes':'No';
const month=x=>x?Math.round((Date.UTC(Number(String(x).slice(0,4)),Number(String(x).slice(5,7))-1,1)-Date.UTC(1899,11,30))/86400000):null;
const cols=n=>{let s='';for(;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;};
const wb=Workbook.create();
const sheets=Object.fromEntries(['Results','Strategies','Selection','Reporting','Sensitivities','Sources'].map(name=>[name,wb.worksheets.add(name)]));
const mappings={};
function base(s,lastCol,lastRow){s.showGridLines=false;s.getRange(`A1:${cols(lastCol)}${lastRow}`).format={font:{name:font,size:11,color:'#000000'},rowHeight:21,columnWidth:15,verticalAlignment:'center'};}
function title(s,text){s.getRange('A2').values=[[text]];s.getRange('A2').format={font:{name:font,size:16,bold:true,color:'#000000'},rowHeight:30};}
function note(s,row,text,end='J',height=33){s.getRange(`A${row}:${end}${row}`).merge();s.getRange(`A${row}`).values=[[text]];s.getRange(`A${row}:${end}${row}`).format={wrapText:true,rowHeight:height,font:{name:font,size:11,color:'#000000'}};}
function section(s,row,text){s.getRange(`A${row}`).values=[[text]];s.getRange(`A${row}`).format={font:{name:font,size:12,bold:true,color:'#000000'},rowHeight:26};}
function table(s,row,headers,values,key){
 const end=cols(headers.length);s.getRange(`A${row}:${end}${row}`).values=[headers];
 s.getRange(`A${row}:${end}${row}`).format={fill:'#E7E6E6',font:{name:font,size:11,bold:true,color:'#000000'},wrapText:true,rowHeight:44,horizontalAlignment:'center',borders:{bottom:{style:'thin',color:'#000000'}}};
 if(values.length)s.getRange(`A${row+1}:${end}${row+values.length}`).values=values;
 if(key)mappings[key]={sheet:s.name,header:row,start:row+1,end:row+values.length,columns:headers,values};
 return row+values.length;
}
function widths(s,last,spec){for(const [column,width]of Object.entries(spec))s.getRange(`${column}1:${column}${last}`).format.columnWidth=width;}
function fmt(s,columns,start,end,format){for(const c of columns)s.getRange(`${c}${start}:${c}${end}`).setNumberFormat(format);}
function formulas(s,column,start,end,make){s.getRange(`${column}${start}:${column}${end}`).formulas=Array.from({length:end-start+1},(_,i)=>[make(start+i)]);}
function conditionalCount(row,field){const value=row[field]*row.changed_paths;const rounded=Math.round(value);if(Math.abs(value-rounded)>1e-9)throw Error('Conditional count not an integer');return rounded;}

// Strategy-level data own the descriptive count and frequency calculations.
const strategies=sheets.Strategies;base(strategies,28,805);title(strategies,'Strategy statistics and descriptive counts');
note(strategies,3,'Common period: January 2017–December 2025. Source stock portfolios are gross of trading, borrowing and management costs.','K');
const summaryRows=[];
for(const weighting of ['original','value_weighted'])for(const representation of ['spread','funded']){
 const subset=stats.filter(r=>r.weighting===weighting&&r.representation===representation);
 summaryRows.push([weight(weighting),series(representation),subset.length,subset.filter(r=>r.conventional_any).length,null,subset.filter(r=>r.conventional_bias).length,subset.filter(r=>r.conventional_normal).length]);
}
table(strategies,5,['Weighting','Return series','Strategies','Either-rule alerts','Alert fraction','Bias alerts','Normal-count alerts'],summaryRows,'strategy_summary');
formulas(strategies,'E',6,9,r=>`=D${r}/C${r}`);fmt(strategies,['E'],6,9,'0.00%');
note(strategies,11,'Alert fractions concern unmodified reconstructed portfolios. They do not estimate dishonest reporting among real funds.','K',30);
const fundStats=stats.filter(r=>r.weighting==='fund_x').sort((a,b)=>a.months-b.months);
table(strategies,13,['Fund X sample','Months','Mean / SD (h)','Excess Sharpe','Bias ratio','Normal-count p','Either-rule alert','FF3 alpha / month'],fundStats.map(r=>[r.months===108?'Common period':'Full supplied period',r.months,r.zero_h,r.excess_sharpe,r.B,r.normal_p,yes(r.conventional_any),r.ff3_alpha]),'fund_summary');
fmt(strategies,['C','D','E'],14,15,'0.0000');fmt(strategies,['F'],14,15,'0.000000');fmt(strategies,['H'],14,15,'0.00%');
section(strategies,18,'One row per strategy, weighting and return series');
const statsRows=stats.map(r=>[r.signal,weight(r.weighting),series(r.representation),r.cohort,month(r.start),month(r.end),r.months,r.excess_sharpe,r.zero_h,r.ff3_alpha,r.ff3_alpha_t_hac4,r.mean,r.sd,r.skew,r.kurtosis,r.acf1,r.B,r.D,r.normal_p,r.negative,yes(r.conventional_bias),yes(r.conventional_normal),yes(r.conventional_any),r.publication_year,r.source_original_weight,r.source_sample_end_year,r.signal_description,r.sharpe_quintile]);
const statsEnd=table(strategies,19,['Signal','Weighting','Return series','Cohort','Start','End','Months','Monthly excess Sharpe','Mean / SD (h)','FF3 alpha / month','FF3 alpha t (HAC4)','Monthly mean','Monthly SD','Skewness','Excess kurtosis','Lag-1 correlation','Bias ratio B','Loss deficit D','Normal-count p','Loss months','Bias alert','Normal-count alert','Either-rule alert','Publication year','Original weight','Original sample end year','Signal description','Sharpe quintile'],statsRows,'strategy_statistics');
for(let r=6;r<=9;r++){
 strategies.getRange(`C${r}`).formulas=[[`=COUNTIFS($B$20:$B$${statsEnd},A${r},$C$20:$C$${statsEnd},B${r})`]];
 for(const [column,flag]of [['D','W'],['F','U'],['G','V']])strategies.getRange(`${column}${r}`).formulas=[[`=COUNTIFS($B$20:$B$${statsEnd},A${r},$C$20:$C$${statsEnd},B${r},$${flag}$20:$${flag}$${statsEnd},"Yes")`]];
}
fmt(strategies,['E','F'],20,statsEnd,'mmm-yy');fmt(strategies,['H','I','K','N','O','P','Q','R'],20,statsEnd,'0.0000');fmt(strategies,['J','L','M'],20,statsEnd,'0.00%');fmt(strategies,['S'],20,statsEnd,'0.000000');fmt(strategies,['G','T','X','Z','AB'],20,statsEnd,'#,##0');
widths(strategies,805,{A:25,B:20,C:25,D:30,E:13,F:13,G:13,H:18,I:16,J:18,K:19,L:16,M:16,N:15,O:16,P:18,Q:15,R:16,S:18,T:14,U:17,V:19,W:18,X:16,Y:16,Z:20,AA:52,AB:17});strategies.freezePanes.freezeRows(19);strategies.freezePanes.freezeColumns(3);
strategies.getRange('G14:G15').format.horizontalAlignment='center';strategies.getRange(`U20:W${statsEnd}`).format.horizontalAlignment='center';

// Exact winner probabilities on each fixed observed matrix.
const observed=[...observedOP,...observedVW];
const boot=[...calOP,...calVW,...bootOP,...bootVW];
const primaryBoot=boot.filter(r=>r.block===12);const secondaryBoot=boot.filter(r=>r.block===6);
const selection=sheets.Selection;base(selection,16,1250);title(selection,'Observed selection and historical resampling');
note(selection,3,'Winner probabilities integrate over all uniformly chosen K-strategy subsets of this fixed panel. They are not counts divided by K.','K',32);
note(selection,4,'Full-panel alerts count all 194 strategies; winner probabilities concern only the highest historical excess-Sharpe strategy in each subset.','K',32);
const selectionRows=observed.map(r=>[weight(r.weighting),series(r.representation),r.months,month(r.end),method(r.method),r.K,r.n_strategies,r.alert_count,null,r.rate]);
const selectionEnd=table(selection,6,['Weighting','Return series','Months','Window end','Screen','Candidates K','Full panel N','Full-panel alerts','Full-panel alert fraction','Exact winner alert probability'],selectionRows,'observed_selection');
formulas(selection,'I',7,selectionEnd,r=>`=H${r}/G${r}`);fmt(selection,['I','J'],7,selectionEnd,'0.00%');fmt(selection,['D'],7,selectionEnd,'mmm-yy');
const observedIndex=new Map(observed.map((r,i)=>[[r.weighting,r.representation,r.months,r.end,r.method,r.K].join('|'),i+7]));
section(selection,selectionEnd+3,'Joint calendar-block resampling: 12-month blocks');
note(selection,selectionEnd+4,'Each row is a conditional historical distribution of alert probabilities. Low and high are the 2.5th and 97.5th percentiles, not confidence limits.','K',32);
const bootStart=selectionEnd+6;
const bootHeaders=['Weighting','Return series','Months','Block months','Source phase','Screen','Candidates K','Draws','Mean alert probability','Median','Range low','Range high','Mean change from K=1 (pp)','Change range low (pp)','Change range high (pp)'];
const bootValues=rows=>rows.map(r=>[weight(r.weighting),series(r.representation),r.months,r.block,r.phase==='evaluation'?'Held-out 2017–2025':'Calibration 2005–2016',method(r.method),r.K,r.draws,r.mean_rate,r.median_rate,r.lo,r.hi,r.mean_change*100,r.change_lo*100,r.change_hi*100]);
const bootEnd=table(selection,bootStart,bootHeaders,bootValues(primaryBoot),'primary_selection_bootstrap');fmt(selection,['I','J','K','L'],bootStart+1,bootEnd,'0.00%');fmt(selection,['M','N','O'],bootStart+1,bootEnd,'0.00');
widths(selection,1250,{A:21,B:24,C:13,D:15,E:28,F:29,G:15,H:17,I:21,J:23,K:17,L:17,M:23,N:23,O:23});selection.freezePanes.freezeRows(6);selection.freezePanes.freezeColumns(2);
selection.getRange(`D7:D${selectionEnd}`).format.horizontalAlignment='center';selection.getRange(`D${bootStart+1}:D${bootEnd}`).format.horizontalAlignment='center';

// Added reporting changes: full panel, designated-candidate selection, resampling.
const reporting=sheets.Reporting;base(reporting,27,1340);title(reporting,'Response to controlled reporting changes');
note(reporting,3,'Small underlying losses are initially replaced by a 0.05% gain. Delayed versions recognize the postponed amount later; permanent versions do not.','L',34);
note(reporting,4,'Baseline and altered fractions use all 194 histories. Conditional fractions use only histories actually changed. These are constructed reporting changes, not observed fraud.','L',34);
const pointValues=reportPoint.map(r=>[weight(r.weighting),series(r.representation),r.months,r.delta,r.probability,recognition(r.lag),method(r.method),r.n_strategies,r.changed_paths,r.baseline_alerts,r.altered_alerts,r.new_alerts,r.cleared_alerts,null,null,null,null,conditionalCount(r,'conditional_baseline_rate'),conditionalCount(r,'conditional_altered_rate'),null,null,r.mean_closing_gap,r.mean_scheduled_future_recognition,r.gap_units,r.paths_with_outstanding_closing_gap]);
const pointEnd=table(reporting,6,['Weighting','Return series','Months','Largest eligible loss','Hiding probability','Recognition','Screen','Histories N','Changed histories','Baseline alerts','Altered alerts','New alerts','Cleared alerts','Baseline fraction','Altered fraction','New-alert fraction','Cleared fraction','Baseline alerts on changed','Altered alerts on changed','Conditional baseline fraction','Conditional altered fraction','Mean closing gap','Scheduled future recognition','Gap units','Histories with closing gap'],pointValues,'reporting_point');
for(const [c,n]of [['N','J'],['O','K'],['P','L'],['Q','M']])formulas(reporting,c,7,pointEnd,r=>`=${n}${r}/H${r}`);
formulas(reporting,'T',7,pointEnd,r=>`=IF(I${r}=0,"n.a.",R${r}/I${r})`);formulas(reporting,'U',7,pointEnd,r=>`=IF(I${r}=0,"n.a.",S${r}/I${r})`);
fmt(reporting,['D','E','N','O','P','Q','T','U','V','W'],7,pointEnd,'0.00%');
const pointIndex=new Map(reportPoint.map((r,i)=>[[r.weighting,r.representation,r.months,r.delta,r.probability,String(r.lag),r.method].join('|'),i+7]));
const selectedHeader=pointEnd+6;
section(reporting,pointEnd+3,'One altered candidate competing with unaltered strategies');
note(reporting,pointEnd+4,'A designated altered candidate competes with K−1 unaltered candidates. Joint probability includes selection and an alert; conditional probability divides by selection.','L',34);
const selectedValues=reportSelected.map(r=>[weight(r.weighting),series(r.representation),r.months,r.delta,r.probability,recognition(r.lag),r.K,method(r.method),r.n_strategies,r.changed_candidates,r.designated_candidate_selection_probability,r.joint_selected_alert_probability,null,r.joint_selected_changed_probability,r.joint_selected_changed_alert_probability,null,r.joint_selected_new_alert_probability,r.population_fraction_designated]);
const selectedEnd=table(reporting,selectedHeader,['Weighting','Return series','Months','Largest eligible loss','Hiding probability','Recognition','Candidates K','Screen','Full panel N','Changed designated candidates','Selection probability','Joint selected + alert','Alert given selected','Joint selected + changed','Joint selected + changed + alert','Alert given changed + selected','Joint selected + new alert','Designated fraction in each pool'],selectedValues,'reporting_selection');
formulas(reporting,'M',selectedHeader+1,selectedEnd,r=>`=IF(K${r}=0,"n.a.",L${r}/K${r})`);formulas(reporting,'P',selectedHeader+1,selectedEnd,r=>`=IF(N${r}=0,"n.a.",O${r}/N${r})`);fmt(reporting,['D','E','K','L','M','N','O','P','Q','R'],selectedHeader+1,selectedEnd,'0.00%');
const reportBootHeader=selectedEnd+6;
section(reporting,selectedEnd+3,'Conditional historical resampling of the 1% loss policy');
note(reporting,selectedEnd+4,'Joint 12-month blocks, 500 resamples. The ranges describe this historical resampling exercise and carry no confidence-coverage guarantee.','L',32);
const reportBootEnd=table(reporting,reportBootHeader,['Weighting','Return series','Recognition','Screen','Draws','Baseline mean','Altered mean','Altered range low','Altered range high','New-alert mean','New-alert range low','New-alert range high','Conditional altered mean','Conditional range low','Conditional range high'],reportBoot.map(r=>[weight(r.weighting),series(r.representation),recognition(r.lag),method(r.method),r.draws,r.baseline_rate_mean,r.altered_rate_mean,r.altered_rate_lo,r.altered_rate_hi,r.new_alert_rate_mean,r.new_alert_rate_lo,r.new_alert_rate_hi,r.conditional_altered_rate_mean,r.conditional_altered_rate_lo,r.conditional_altered_rate_hi]),'reporting_bootstrap');fmt(reporting,['F','G','H','I','J','K','L','M','N','O'],reportBootHeader+1,reportBootEnd,'0.00%');
widths(reporting,1340,{A:21,B:24,C:12,D:29,E:19,F:18,G:29,H:29,I:18,J:17,K:17,L:16,M:17,N:19,O:19,P:19,Q:19,R:21,S:21,T:23,U:23,V:20,W:23,X:31,Y:22});reporting.freezePanes.freezeRows(6);reporting.freezePanes.freezeColumns(2);
reporting.getRange(`F7:F${selectedEnd}`).format.horizontalAlignment='center';reporting.getRange(`G${selectedHeader+1}:G${selectedEnd}`).format.horizontalAlignment='center';

// Robustness, descriptive associations and exploratory fixed combinations.
const sensitivity=sheets.Sensitivities;base(sensitivity,23,1200);title(sensitivity,'Sensitivity and exploratory results');
note(sensitivity,3,'Weighting, funding, history length and block length change the reference. The tables keep those choices separate.','L',30);
section(sensitivity,5,'Joint calendar-block resampling: 6-month blocks');
const blockEnd=table(sensitivity,6,bootHeaders,bootValues(secondaryBoot),'secondary_selection_bootstrap');fmt(sensitivity,['I','J','K','L'],7,blockEnd,'0.00%');fmt(sensitivity,['M','N','O'],7,blockEnd,'0.00');
let at=blockEnd+4;section(sensitivity,at,'Reporting-policy randomization on fixed observed histories');
note(sensitivity,at+1,'100 policy draws per row. MCSE measures only randomization error in the reporting policy; it is not uncertainty about a wider fund population.','L',32);
const randomHeader=at+3;
const randomEnd=table(sensitivity,randomHeader,['Weighting','Return series','Policy','Largest eligible loss','Recognition','Screen','Policy draws','Mean changed histories','Baseline mean','Altered mean','Policy MCSE','New-alert mean','New-alert MCSE','Conditional altered mean','Conditional MCSE'],reportSensitivity.map(r=>[weight(r.weighting),series(r.representation),r.policy.replaceAll('_',' '),r.delta,recognition(r.lag),method(r.method),r.policy_draws,r.mean_changed_paths,r.baseline_rate_mean,r.altered_rate_mean,r.altered_rate_mcse,r.new_alert_rate_mean,r.new_alert_rate_mcse,r.conditional_altered_rate_mean,r.conditional_altered_rate_mcse]),'reporting_sensitivity');fmt(sensitivity,['D','I','J','K','L','M','N','O'],randomHeader+1,randomEnd,'0.00%');fmt(sensitivity,['H'],randomHeader+1,randomEnd,'0.0');
at=randomEnd+4;section(sensitivity,at,'Symmetric smoothing: current and previous returns');
note(sensitivity,at+1,'Filtered return = (1−lambda) × current return + lambda × previous return. Both gains and losses move; this diagnostic does not identify intent.','L',32);
const smoothHeader=at+3;
const smoothEnd=table(sensitivity,smoothHeader,['Weighting','Return series','Months','Lambda','Screen','Histories N','Baseline alerts','Filtered alerts','New alerts','Cleared alerts','Baseline fraction','Filtered fraction','Mean lag-1 before','Mean lag-1 after','Median B before','Median B after','Mean D before','Mean D after'],smoothing.map(r=>[weight(r.weighting),series(r.representation),r.months,r.lambda,method(r.method),r.n_strategies,r.baseline_alerts,r.filtered_alerts,r.new_alerts,r.cleared_alerts,null,null,r.mean_acf_before,r.mean_acf_after,r.median_B_before,r.median_B_after,r.mean_D_before,r.mean_D_after]),'smoothing');formulas(sensitivity,'K',smoothHeader+1,smoothEnd,r=>`=G${r}/F${r}`);formulas(sensitivity,'L',smoothHeader+1,smoothEnd,r=>`=H${r}/F${r}`);fmt(sensitivity,['D','K','L'],smoothHeader+1,smoothEnd,'0.00%');fmt(sensitivity,['M','N','O','P','Q','R'],smoothHeader+1,smoothEnd,'0.000');
at=smoothEnd+4;section(sensitivity,at,'Exploratory combinations with weights estimated before 2017');
note(sensitivity,at+1,'Added after inspecting individual-strategy results. No means were shifted and no diagnostic cutoffs were refitted. These portfolios remain gross of costs.','L',34);
const comboHeader=at+3;
const comboEnd=table(sensitivity,comboHeader,['Weighting','Combination rule','Return series','Months','Monthly excess Sharpe','Mean / SD (h)','Monthly mean','Monthly SD','Bias ratio B','Loss deficit D','Normal-count p','Loss months','Bias alert','Normal-count alert','Either-rule alert','Calibration excess Sharpe','Largest weight','Positive weights','Weight sum'],combinations.map(r=>[weight(r.weighting),rule(r.rule),series(r.representation),r.months,r.excess_sharpe,r.zero_h,r.mean,r.sd,r.B,r.D,r.normal_p,r.negative,yes(r.conventional_bias),yes(r.conventional_normal),yes(r.conventional_any),r.calibration_spread_h,r.max_weight,r.positive_weights,r.sum_weights]),'exploratory_combinations');fmt(sensitivity,['E','F','I','J','P','S'],comboHeader+1,comboEnd,'0.0000');fmt(sensitivity,['G','H','Q'],comboHeader+1,comboEnd,'0.00%');fmt(sensitivity,['K'],comboHeader+1,comboEnd,'0.000000');
at=comboEnd+4;section(sensitivity,at,'Sharpe quintiles: original-paper weighting');
const quintHeader=at+2;
const quintEnd=table(sensitivity,quintHeader,['Return series','Sharpe quintile','Screen','Strategies','Alerts','Alert fraction','Minimum excess Sharpe','Maximum excess Sharpe','Mean excess Sharpe','Mean skewness','Mean excess kurtosis','Mean lag-1 correlation'],quintiles.map(r=>[series(r.representation),r.quintile,method(r.method),r.n_strategies,r.alert_count,null,r.min_excess_sharpe,r.max_excess_sharpe,r.mean_excess_sharpe,r.mean_skew,r.mean_kurtosis,r.mean_acf1]),'quintiles');formulas(sensitivity,'F',quintHeader+1,quintEnd,r=>`=E${r}/D${r}`);fmt(sensitivity,['F'],quintHeader+1,quintEnd,'0.00%');fmt(sensitivity,['G','H','I','J','K','L'],quintHeader+1,quintEnd,'0.000');
const quintIndex=new Map(quintiles.map((r,i)=>[[r.weighting,r.representation,r.quintile,r.method].join('|'),quintHeader+1+i]));
at=quintEnd+4;section(sensitivity,at,'Descriptive ridge-logit associations');
note(sensitivity,at+1,'Outcome: either conventional alert. Features are standardized within each fit. Rare alerts and zero-alert panels limit interpretation; these are not causal effects.','L',34);
note(sensitivity,at+2,'The low/high columns are conditional block-refit percentiles. Threshold events can put the observed coefficient outside that range.','L',30);
const logitHeader=at+4;
const logitEnd=table(sensitivity,logitHeader,['Weighting','Return series','Term','Observed coefficient','Refit range low','Refit range high','Feature mean','Feature SD','Observed alert fraction','Block draws','Block months','Strategies'],logit.map(r=>[weight(r.weighting),series(r.representation),r.term.replaceAll('_',' '),r.coefficient,r.lo,r.hi,r.feature_mean,r.feature_sd,r.point_flag_rate,r.bootstrap_draws,r.block_months,r.n_strategies]),'descriptive_logit');fmt(sensitivity,['D','E','F','G','H'],logitHeader+1,logitEnd,'0.0000');fmt(sensitivity,['I'],logitHeader+1,logitEnd,'0.00%');
widths(sensitivity,Math.max(1200,logitEnd),{A:21,B:29,C:28,D:20,E:29,F:29,G:18,H:22,I:22,J:21,K:21,L:21,M:23,N:23,O:23,P:23,Q:20,R:20,S:20});sensitivity.freezePanes.freezeRows(6);sensitivity.freezePanes.freezeColumns(2);
sensitivity.getRange(`D7:D${blockEnd}`).format.horizontalAlignment='center';sensitivity.getRange(`D${smoothHeader+1}:D${smoothEnd}`).format.horizontalAlignment='center';sensitivity.getRange(`M${comboHeader+1}:O${comboEnd}`).format.horizontalAlignment='center';

// Definitions and frozen source records are visible, separate from results.
const sources=sheets.Sources;base(sources,8,160);title(sources,'Data, definitions and fixed choices');
const definitions=[
 ['Common period','January 2017–December 2025: 108 months. The public release ends in 2025, so Fund X’s 2026 observations do not enter benchmark comparisons.'],
 ['Descriptive cohort','195 strategies have complete common-period returns. Publication years are no later than 2016; original reported samples end no later than 2014.'],
 ['Calibrated core','194 of the same strategies also have complete 2005–2016 calibration data. DivOmit is excluded; exactly the same names enter the value-weighted comparison.'],
 ['Development','1980–2004 December-end windows. At 108 months: 3,148 eligible strategy-windows across 193 strategies and 17 endpoints. DelDRC has no complete development window.'],
 ['Calibration','2005–2016, before the 2017–2025 evaluation. Every reported K enters the common selection-reference cutoff.'],
 ['Evaluation','2017–2025 is held out from map and cutoff fitting. Retrospective data revisions and catalogue selection remain.'],
 ['Primary implementation','Original-paper sorts and original weighting: some sorts are equal-weighted and some value-weighted. The matched forced-value version changes weighting only.'],
 ['Units and stock payoff','Source percent returns are divided by 100 once. Long-short means long-leg return minus short-leg return. It is already a zero-investment payoff; do not subtract cash again.'],
 ['Funding sensitivity','Cash return + one unit of long-short payoff per unit collateral: $1 long and $1 short, gross stock notional 2. Source returns omit execution, borrowing and management costs.'],
 ['Sharpe and h','Monthly excess Sharpe = mean excess payoff / sample SD of excess payoff. h = mean of the actual diagnostic series / its sample SD. They differ for Fund X and funded series.'],
 ['Factor alpha','Monthly intercept in US Fama–French three-factor regression. Long-short spread enters directly; funded and Fund X total returns enter net of cash. t statistics use HAC with 4 lags.'],
 ['Conventional rules','Bias ratio B > 2 or fitted-normal lower binomial tail p < 0.05. Combined means either rule. This Gaussian adaptation is not the original Bollen–Pool test.'],
 ['Bias ratio B','Count of returns in [0,SD], divided by 1 plus count in [−SD,0). Losses are strictly negative; the +1 convention is retained throughout.'],
 ['Loss deficit D','Expected negative months under a fitted normal, T × Phi(−h), minus observed negative months. Larger values mean fewer losses than that reference predicts.'],
 ['Calibrated score','C is the larger development-period empirical rank of B and D. These ranks are not p-values. A strict score > cutoff triggers an alert.'],
 ['Ordinary reference','Empirical 95th percentile for K=1 in the joint calendar-block calibration resamples.'],
 ['Selection reference','Largest empirical 95th percentile across K = 1, 5, 20, 50, 100, 194 in calibration. This is a finite conditional historical reference, not a universal 5% guarantee.'],
 ['Exact selection','Uniformly choose K distinct strategies from the fixed panel and retain the highest historical excess Sharpe. Rank-j winner weight is C(N−j,K−1) / C(N,K).'],
 ['Bootstrap ranges','Common calendar indices resample all strategies and cash together, in circular time blocks. Low/high are 2.5th/97.5th percentiles conditional on the source history; no exact confidence coverage is claimed.'],
 ['Reporting changes','Eligible underlying losses at most delta are replaced initially by a 0.05% gain. Permanent or 1-, 3-, 6-month recognition rules use separate payoff and log-NAV accounting.'],
 ['Closing reporting gaps','No forced recognition in the last observation. Delayed gaps have a scheduled future settlement; the available evaluation sample supplies no actual economic return tail.'],
 ['Selected reporting policy','One designated altered candidate is included with K−1 unaltered candidates. Selection, selected-plus-alert, and alert-given-selection probabilities have separate denominators.'],
 ['Smoothing','Symmetric causal filter: (1−lambda) × current + lambda × previous, lambda = 0.25, 0.50, 0.75. It moves gains and losses alike.'],
 ['Exploratory combinations','Equal-notional, inverse-volatility and capped maximum-Sharpe weights use 2005–2016 only. Added after individual results; no calibrated flags are claimed for these new combined strategies.'],
 ['What this does establish','Responses of specified return screens to observed reconstructed stock strategies and explicitly added reporting changes.'],
 ['What remains unidentified','Actual false accusations, real-world fraud detection, investor authentication and general fund-population error rates. The strategies share stocks and market months.'],
 ['Fund X comparison','Fund X is a reported net fund return; source portfolios are gross stock-strategy payoffs. Individual strategies do not reach Fund X’s common-period h. No benchmark means were shifted to close this gap.'],
 ['Excel calculations','Excel recalculates displayed fractions and conditional probabilities from their saved components. Refitting scores, portfolio weights or resampling requires the accompanying analysis code.']
 ];
table(sources,5,['Item','Definition'],definitions,'definitions');for(let r=5;r<=5+definitions.length;r++)sources.getRange(`B${r}:H${r}`).merge();sources.getRange(`B6:H${5+definitions.length}`).format.wrapText=true;sources.getRange(`A6:H${5+definitions.length}`).format.rowHeight=54;
const sourceHeader=definitions.length+9;
const sourceRecords=[['Paper','Chen and Zimmermann (2022), Open Source Cross-Sectional Asset Pricing, Critical Finance Review 11(2), 207–264.','https://www.openassetpricing.com/'],['Data release',`2026.10; frozen dataset commit ${provenance.dataset_commit}`,'https://huggingface.co/datasets/OpenSourceAP/CrossSection/tree/'+provenance.dataset_commit],...provenance.sources.map(r=>[path.basename(r.file),r.sha256,r.source_url??r.source]),['Source code','v2.1.0; commit 9f053398c4995651d822e90d81526d0644c6f3e5','https://github.com/OpenSourceAP/CrossSection/tree/9f053398c4995651d822e90d81526d0644c6f3e5'],['Attribution','Published CZ portfolio files: CC BY 4.0. Credit Andrew Y. Chen and Tom Zimmermann.','https://creativecommons.org/licenses/by/4.0/'],['Current paper and note','Professor-supplied full paper package and Chen–Zimmermann screening note. Inputs retained unchanged.','Project input archive'],['Exploratory weight rules',comboDesign.status,'Weights and monthly combined returns retained in the accompanying result tables.']];
section(sources,sourceHeader-2,'Frozen source files');const sourcesEnd=table(sources,sourceHeader,['Source','Version / SHA-256 / description','Location'],sourceRecords,'source_records');sources.getRange(`B${sourceHeader+1}:C${sourcesEnd}`).format.wrapText=true;sources.getRange(`A${sourceHeader+1}:C${sourcesEnd}`).format.rowHeight=72;
for(let r=sourceHeader;r<=sourcesEnd;r++)sources.getRange(`C${r}:H${r}`).merge();sources.getRange(`C${sourceHeader+1}:H${sourcesEnd}`).format.wrapText=true;
const cutoffHeader=sourcesEnd+5;section(sources,sourcesEnd+3,'Exact stored score cutoffs');
const cutoffRows=[];
for(const [id,r]of Object.entries(cutoffs.rules)){const [w,k,t,b]=id.split(':');for(const pool of r.per_pool)cutoffRows.push([weight(w),series(k),Number(t),Number(b.slice(1)),pool.K,pool.cutoff,r.ordinary,r.selection]);}
const cutoffEnd=table(sources,cutoffHeader,['Weighting','Return series','Months','Block months','Candidates K','K-specific cutoff','Ordinary cutoff','Selection cutoff'],cutoffRows,'locked_cutoffs');fmt(sources,['F','G','H'],cutoffHeader+1,cutoffEnd,'0.000000000000000');
widths(sources,cutoffEnd,{A:29,B:32,C:18,D:18,E:18,F:24,G:24,H:24});sources.freezePanes.freezeRows(5);

// Summary links to the relevant owning tables.
const results=sheets.Results;base(results,10,76);title(results,'Chen–Zimmermann return-screening results');
note(results,3,'108 common months, January 2017–December 2025. The new evidence supports a limited due-diligence comparison, not authentication of Fund X.','J',34);
section(results,5,'Unmodified benchmark portfolios');
table(results,6,['Weighting','Return series','Strategies','Either-rule alerts','Alert fraction'],summaryRows.map((r,i)=>[r[0],r[1],null,null,null]),'headline_descriptive');
for(let i=0;i<4;i++)results.getRange(`C${7+i}:E${7+i}`).formulas=[[`='Strategies'!C${6+i}`,`='Strategies'!D${6+i}`,`='Strategies'!E${6+i}`]];fmt(results,['E'],7,10,'0.00%');
table(results,12,['Main calibrated core','Strategies','Selection-reference alerts','Alert fraction'],[['Original-paper spread',design.core_signals.length,null,null]],'headline_calibrated');
const coreRow=observedIndex.get('original|spread|108|2025-12|selection_calibrated|1');if(!coreRow)throw Error('Missing core headline');
results.getRange('C13:D13').formulas=[[`='Selection'!H${coreRow}`,`='Selection'!I${coreRow}`]];fmt(results,['D'],13,13,'0.00%');
note(results,15,'One original-paper spread triggers a conventional alert; four trigger after adding cash. Forced-value portfolios have no conventional alerts in this snapshot.','J',34);
section(results,17,'Performance range matters');
table(results,18,['Common-period series','Monthly mean / SD (h)','Monthly excess Sharpe'],[['Fund X',null,null],['Highest individual original-paper spread',descmeta.primary_highest_h.h,descmeta.primary_highest_h.h]],'headline_performance');results.getRange('B19:C19').formulas=[["='Strategies'!C14","='Strategies'!D14"]];fmt(results,['B','C'],19,20,'0.0000');
note(results,22,`The highest individual strategy is ${descmeta.primary_highest_h.signal}. None of the 195 individual original-paper spreads reaches Fund X’s h.`, 'J',30);
section(results,24,'Conventional alerts across excess-Sharpe quintiles');
table(results,25,['Sharpe quintile (1 low, 5 high)','Strategies','Either-rule alerts','Alert fraction'],Array.from({length:5},(_,i)=>[i+1,null,null,null]),'headline_quintiles');
for(let i=0;i<5;i++){const r=quintIndex.get(`original|spread|${i+1}|conventional_any`);if(!r)throw Error('Missing quintile');results.getRange(`B${26+i}:D${26+i}`).formulas=[[`='Sensitivities'!D${r}`,`='Sensitivities'!E${r}`,`='Sensitivities'!F${r}`]];}fmt(results,['D'],26,30,'0.00%');
section(results,33,'Highest-Sharpe selection on the observed 194-strategy panel');
table(results,34,['Candidates K','Conventional winner alert probability','Ordinary-reference winner alert probability','Selection-reference winner alert probability'],[1,5,20,50,100,194].map(k=>[k,null,null,null]),'headline_selection');
for(let i=0;i<6;i++)for(const [column,m]of [['B','conventional_any'],['C','ordinary_calibrated'],['D','selection_calibrated']]){const r=observedIndex.get(`original|spread|108|2025-12|${m}|${[1,5,20,50,100,194][i]}`);results.getRange(`${column}${35+i}`).formulas=[[`='Selection'!J${r}`]];}fmt(results,['B','C','D'],35,40,'0.00%');
note(results,42,'These are exact subset-winner probabilities for this observed panel. Conditional resampling results are on Selection; historical cutoffs can behave differently in the held-out period.','J',34);
section(results,44,'Hide every loss of at most 1%: permanent versus three-month recognition');
table(results,45,['Return series','Recognition','Screen','Baseline alerts','Altered alerts','Changed histories','Histories N','Altered fraction','New-alert fraction','Alert fraction among changed'],['spread','funded'].flatMap(k=>['permanent','3'].flatMap(l=>['conventional_any','selection_calibrated'].map(m=>[series(k),recognition(l),method(m),null,null,null,null,null,null,null]))),'headline_reporting');
let rr=46;
for(const k of ['spread','funded'])for(const l of ['permanent','3'])for(const m of ['conventional_any','selection_calibrated']){const r=pointIndex.get(`original|${k}|108|0.01|1|${l}|${m}`);if(!r)throw Error('Missing reporting headline');results.getRange(`D${rr}:J${rr}`).formulas=[[`='Reporting'!J${r}`,`='Reporting'!K${r}`,`='Reporting'!I${r}`,`='Reporting'!H${r}`,`='Reporting'!O${r}`,`='Reporting'!P${r}`,`='Reporting'!U${r}`]];rr++;}fmt(results,['H','I','J'],46,53,'0.00%');
note(results,55,'Tight historical calibration reduces unmodified alerts but can miss the added reporting changes, particularly when losses reappear later. A quiet screen does not verify returns.','J',34);
section(results,57,'Exploratory diversification, with weights estimated in 2005–2016');
const comboMain=combinations.filter(r=>r.weighting==='original'&&r.representation==='spread');
table(results,58,['Combination rule','Monthly excess Sharpe','Mean / SD (h)','Bias ratio','Normal-count p','Either-rule alert'],comboMain.map(r=>[rule(r.rule),r.excess_sharpe,r.zero_h,r.B,r.normal_p,yes(r.conventional_any)]),'headline_combinations');fmt(results,['B','C','D'],59,61,'0.0000');fmt(results,['E'],59,61,'0.000000');
for(let i=0;i<comboMain.length;i++){
 const source=combinations.findIndex(r=>r.weighting===comboMain[i].weighting&&r.representation===comboMain[i].representation&&r.rule===comboMain[i].rule)+comboHeader+1;
 results.getRange(`B${59+i}:F${59+i}`).formulas=[[`='Sensitivities'!E${source}`,`='Sensitivities'!F${source}`,`='Sensitivities'!I${source}`,`='Sensitivities'!K${source}`,`='Sensitivities'!O${source}`]];
}
results.getRange('F59:F61').format.horizontalAlignment='center';
note(results,63,'Diversification moves the benchmark performance range closer to Fund X. It does not supply independent net hedge-fund returns or a labelled fraud sample.','J',32);
note(results,65,'The practical contribution is to show how selection, the return convention and later loss recognition change what a return screen can tell an investor. The scope remains narrow.','J',34);
section(results,67,'Largest held-out conditional mean for the selection-reference rule');
const worst=boot.filter(r=>r.phase==='evaluation'&&r.method==='selection_calibrated').reduce((a,b)=>a.mean_rate>b.mean_rate?a:b);
table(results,68,['Weighting','Return series','Months','Candidates K','Mean alert probability','Block months','Range low','Range high'],[[weight(worst.weighting),series(worst.representation),worst.months,worst.K,null,worst.block,null,null]],'headline_historical_failure');
const worstArray=worst.block===12?primaryBoot:secondaryBoot;const worstHeader=worst.block===12?bootStart:6;const worstSheet=worst.block===12?'Selection':'Sensitivities';const worstRow=worstArray.indexOf(worst)+worstHeader+1;
results.getRange('E69').formulas=[[`='${worstSheet}'!I${worstRow}`]];results.getRange('G69:H69').formulas=[[`='${worstSheet}'!K${worstRow}`,`='${worstSheet}'!L${worstRow}`]];fmt(results,['E','G','H'],69,69,'0.00%');
note(results,71,'The 5% calibration reference does not ensure a 5% held-out alert rate. The range concerns joint historical resampling, not a wider population of funds.','J',34);
widths(results,76,{A:33,B:27,C:30,D:20,E:20,F:20,G:16,H:19,I:20,J:23});results.freezePanes.freezeRows(6);

wb.recalculate();
const before=reporting.getRange('O7').values[0][0];const count=reporting.getRange('K7').values[0][0];const n=reporting.getRange('H7').values[0][0];
reporting.getRange('K7').values=[[count+1]];wb.recalculate();const perturbed=reporting.getRange('O7').values[0][0];
if(Math.abs(perturbed-(count+1)/n)>1e-12)throw Error('Altered fraction failed recalculation');
reporting.getRange('K7').values=[[count]];wb.recalculate();if(Math.abs(reporting.getRange('O7').values[0][0]-before)>1e-12)throw Error('Altered fraction failed restoration');
const scan=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:100},summary:'Final formula error scan'});await fs.writeFile(path.join(qa,'workbook_formula_scan.ndjson'),scan.ndjson);
const check=await wb.inspect({kind:'table',range:'Results!A6:E13',include:'values,formulas',tableMaxRows:8,tableMaxCols:5,maxChars:5000});await fs.writeFile(path.join(qa,'workbook_headline_check.ndjson'),check.ndjson);
const renderSpecs=[['Results','A1:J22','results_top.png'],['Results','A24:J42','results_selection.png'],['Results','A44:J71','results_reporting.png'],['Strategies','A1:K15','strategies_summary.png'],['Strategies','A18:K25','strategies_detail.png'],['Strategies','L18:W25','strategies_scores.png'],['Selection','A1:K14','selection_observed.png'],['Selection',`A${bootStart-3}:O${bootStart+6}`,'selection_resampling.png'],['Reporting','A1:O13','reporting_point.png'],['Reporting',`A${selectedHeader-3}:R${selectedHeader+5}`,'reporting_selected.png'],['Reporting',`A${reportBootHeader-3}:O${reportBootHeader+5}`,'reporting_resampling.png'],['Sensitivities','A1:O12','sensitivity_block.png'],['Sensitivities',`A${smoothHeader-3}:R${smoothHeader+5}`,'sensitivity_smoothing.png'],['Sensitivities',`A${comboHeader-3}:S${comboHeader+5}`,'sensitivity_combinations.png'],['Sensitivities',`A${logitHeader-4}:L${logitHeader+6}`,'sensitivity_logit.png'],['Sources','A1:H16','sources_definitions.png'],['Sources',`A${sourceHeader-2}:H${sourceHeader+4}`,'sources_records.png'],['Sources',`A${cutoffHeader-2}:H${cutoffHeader+5}`,'sources_cutoffs.png']];
for(const [name,range,file]of renderSpecs){const png=await wb.render({sheetName:name,range,scale:1,format:'png'});await fs.writeFile(path.join(qa,file),new Uint8Array(await png.arrayBuffer()));console.log('Rendered '+file);}
const outputPath=path.join(root,'Assignment_9_Chen_Zimmermann_Screening.xlsx');const output=await SpreadsheetFile.exportXlsx(wb);await output.save(outputPath);
try{await fs.rename(outputPath+'.inspect.ndjson',path.join(qa,'workbook_export_inspection.ndjson'));}catch(e){if(e.code!=='ENOENT')throw e;}
const outputDir=path.resolve(root,'../../outputs/assignment_9_chEN_zimmermann');await fs.mkdir(outputDir,{recursive:true});await fs.copyFile(outputPath,path.join(outputDir,path.basename(outputPath)));
const formulaCells={};for(const [key,m]of Object.entries(mappings)){const s=sheets[m.sheet];m.values=s.getRange(`A${m.start}:${cols(m.columns.length)}${m.end}`).values;for(let r=m.start;r<=m.end;r++){const f=s.getRange(`A${r}:${cols(m.columns.length)}${r}`).formulas[0];f.forEach((v,c)=>{if(v)formulaCells[`${m.sheet}!${cols(c+1)}${r}`]=v;});}}
const evidence={sheets:Object.keys(sheets),rendered_regions:renderSpecs.map(([sheet,range,file])=>({sheet,range,file})),recalculation:{sheet:'Reporting',input:'K7',output:'O7',original_count:count,denominator:n,original_value:before,perturbed_value:perturbed,restored:true},mappings,formulaCells,source_table_rows:{descriptive:stats.length,observed_selection:observed.length,primary_bootstrap:primaryBoot.length,secondary_bootstrap:secondaryBoot.length,reporting_point:reportPoint.length,reporting_selection:reportSelected.length,reporting_bootstrap:reportBoot.length,reporting_sensitivity:reportSensitivity.length,smoothing:smoothing.length,combinations:combinations.length},frozen_design_sha256:createHash('sha256').update(await fs.readFile(path.join(root,'data/frozen_design.json'))).digest('hex'),locked_cutoffs_sha256:createHash('sha256').update(await fs.readFile(path.join(root,'data/locked_cutoffs.json'))).digest('hex')};
await fs.writeFile(path.join(qa,'workbook_build_checks.json'),JSON.stringify(evidence,null,2));
console.log(JSON.stringify({output:outputPath,output_copy:path.join(outputDir,path.basename(outputPath)),source_table_rows:evidence.source_table_rows,recalculation:evidence.recalculation}));
