import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const qa=path.resolve(root,'../../.qa_assignment7');
const r=JSON.parse(await fs.readFile(path.join(root,'assignment7_results.json'),'utf8'));
async function readCsv(relative){
  const csv=await fs.readFile(path.join(root,relative),'utf8');
  const source=await Workbook.fromCSV(csv,{sheetName:'Source'});
  const [heads,...rows]=source.worksheets.getItemAt(0).getUsedRange().values;
  return rows.filter(row=>row[0]).map(row=>Object.fromEntries(heads.map((h,i)=>[h,['date','month'].includes(h)?String(row[i]):Number(row[i])])));
}
const input={monthly:await readCsv('tables/monthly_model_results.csv'),forecasts:await readCsv('tables/expanding_forecasts.csv')};
const wb=Workbook.create();
const summary=wb.worksheets.add('Results');
const monthly=wb.worksheets.add('Monthly returns');
const forecast=wb.worksheets.add('Forecast checks');
const sensitivity=wb.worksheets.add('Sensitivity');

function style(sh,range){
  sh.showGridLines=false;
  sh.getRange(range).format.font={name:'Arial',size:10,color:'#202A35'};
  sh.getRange(range).format.verticalAlignment='center';
  sh.getRange(range).format.rowHeight=21;
  sh.getRange(range).format.columnWidth=15;
}
function title(sh,text){sh.getRange('A2').values=[[text]];sh.getRange('A2').format.font={name:'Arial',size:15,bold:true};sh.getRange('A2').format.rowHeight=27;}
function header(sh,range){sh.getRange(range).format={fill:'#344D65',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},rowHeight:30,wrapText:true,horizontalAlignment:'center',verticalAlignment:'center'};}
function section(sh,cell,text){sh.getRange(cell).values=[[text]];sh.getRange(cell).format.font={bold:true};}
style(summary,'A1:H42');title(summary,'Fund X two regime model review');summary.tabColor='#344D65';
summary.getRange('A3').values=[['January 2017 to July 2026. Monthly returns. July is estimated.']];
summary.getRange('A5:F5').values=[['Model','Parameters','Log likelihood','AIC','BIC','Observations']];header(summary,'A5:F5');
summary.getRange('A6:C10').values=r.comparison.map(x=>[x.model,x.parameters,x.log_likelihood]);
summary.getRange('F6:F10').formulas=Array.from({length:5},()=>["=COUNT('Monthly returns'!B6:B120)"]);
summary.getRange('D6:E6').formulas=[['=-2*C6+2*B6','=-2*C6+B6*LN(F6)']];summary.getRange('D6:E10').fillDown();
summary.getRange('C6:E10').setNumberFormat('0.00');
summary.getRange('A12').values=[['Higher likelihood and lower AIC/BIC indicate a better fit after accounting for model size.']];
summary.getRange('A13').values=[['Fit parameters are saved Python estimates. Rerun the calculation script to refit after changing data.']];
section(summary,'A15','State estimates and implied monthly returns');
summary.getRange('A16:H16').values=[['State','Log mean','Log SD','Stay probability','Long-run share','Mean return','Return SD','Duration months']];header(summary,'A16:H16');
const f=r.best,n=r.note_rounded;
summary.getRange('A17:D20').values=[['Note ordinary',n.mu[0],n.sd[0],n.P[0][0]],['Note high',n.mu[1],n.sd[1],n.P[1][1]],['Improved lower',f.mu[0],f.sd[0],f.P[0][0]],['Improved higher',f.mu[1],f.sd[1],f.P[1][1]]];
summary.getRange('E17:E20').formulas=[['=(1-D18)/(2-D17-D18)'],['=1-E17'],['=(1-D20)/(2-D19-D20)'],['=1-E19']];
summary.getRange('F17:H17').formulas=[['=EXP(B17+C17^2/2)-1','=SQRT((EXP(C17^2)-1)*EXP(2*B17+C17^2))','=1/(1-D17)']];summary.getRange('F17:H20').fillDown();
summary.getRange('B17:C20').setNumberFormat('0.0000');summary.getRange('D17:G20').setNumberFormat('0.00%');summary.getRange('H17:H20').setNumberFormat('0.0');
section(summary,'A22','Tests of timing and remaining dependence');
summary.getRange('A23:F23').values=[['Check','Statistic','Exceedances','Simulations','Monte Carlo p','Tail']];header(summary,'A23:F23');
summary.getRange('A24:D25').values=[['Ordering gain vs mixture',r.ordering_test.gain,r.ordering_test.exceedances,r.ordering_test.reps],['Predictive innovation Q12',r.forecast_Q12_bootstrap.Q12,r.forecast_Q12_bootstrap.exceedances,r.forecast_Q12_bootstrap.reps]];
summary.getRange('E24:E24').formulas=[['=(C24+1)/(D24+1)']];summary.getRange('E24:E25').fillDown();summary.getRange('F24:F25').values=[['Upper'],['Upper']];
summary.getRange('B24:B25').setNumberFormat('0.000');summary.getRange('E24:E25').setNumberFormat('0.000');
section(summary,'A27','Data and loss calibration');
summary.getRange('A28:B33').values=[['Observed months',null],['Observed losses',null],['Average monthly return',null],['Monthly sample SD',null],['Note expected loss months',r.note_moments.expected_loss_months],['Improved expected loss months',r.best_moments.expected_loss_months]];
summary.getRange('B28:B31').formulas=[["=COUNT('Monthly returns'!B6:B120)"],["=COUNTIFS('Monthly returns'!B6:B120,\"<0\")"],["=AVERAGE('Monthly returns'!B6:B120)"],["=STDEV.S('Monthly returns'!B6:B120)"]];summary.getRange('B30:B31').setNumberFormat('0.00%');summary.getRange('B32:B33').setNumberFormat('0.0');
summary.getRange('A35').values=[['Ordering p tests exchangeability, not a unique economic cause. Q12 bootstrap refits each sample.']];
summary.getRange('A36').values=[['Expected loss counts are model implications. They are not formal goodness-of-fit p-values.']];
summary.getRange('A38').values=[['Later-month forecasts favor the independent mixture for distribution accuracy. See Forecast checks.']];
summary.getRange('A1:A42').format.columnWidth=38;
summary.getRange('B1:H42').format.columnWidth=15;

style(monthly,'A1:I120');title(monthly,'Monthly returns and fitted state measures');
monthly.getRange('A3').values=[['Source: July 2026 Spartan LSQ factsheet, saved August 10, 2026. All 115 observations reconciled.']];
monthly.getRange('A4').values=[['https://spartanfunds.ca/wp-content/uploads/2021/11/LSQ-Oct21.pdf']];
monthly.getRange('A5:I5').values=[['Month','Simple return','Log return','High state path','Filtered high prob','Predicted high prob','Note high path','Predictive innovation','July estimated']];header(monthly,'A5:I5');
monthly.getRange('A6:I120').values=input.monthly.map(x=>[new Date(x.date+'-01T00:00:00Z'),x.lsq_return,null,x.high_state_viterbi,x.high_probability_filtered,x.high_probability_predicted,x.note_viterbi,x.forecast_innovation,x.date==='2026-07']);
monthly.getRange('C6').formulas=[['=LN(1+B6)']];monthly.getRange('C6:C120').fillDown();
monthly.getRange('A6:A120').setNumberFormat('mmm yyyy');monthly.getRange('B6:C120').setNumberFormat('0.00%');monthly.getRange('E6:F120').setNumberFormat('0.0%');monthly.getRange('H6:H120').setNumberFormat('0.000');monthly.getRange('A1:I120').format.columnWidth=18;monthly.freezePanes.freezeRows(5);
monthly.getRange('K5').values=[['State 1 is the higher-return state.']];monthly.getRange('K6').values=[['Path labels use the full sample.']];monthly.getRange('K7').values=[['Filter probabilities use fitted full-sample parameters.']];monthly.getRange('K8').values=[['Forecast checks refit using only earlier observations.']];

style(forecast,'A1:K33');title(forecast,'Expanding one month ahead checks');
forecast.getRange('A3').values=[['January 2025 to July 2026. Each monthly fit uses earlier data only. Model family selected retrospectively.']];
forecast.getRange('A5:K5').values=[['Month','Actual return','One mean','Mixture mean','Switching mean','One log score','Mixture log score','Switching log score','One squared error','Mixture squared error','Switch squared error']];header(forecast,'A5:K5');
forecast.getRange('A6:H24').values=input.forecasts.map(x=>[new Date(x.date+'-01T00:00:00Z'),x.actual,x.one_mean,x.mixture_mean,x.hmm_mean,x.one_log_score,x.mixture_log_score,x.hmm_log_score]);
forecast.getRange('I6:K6').formulas=[['=(C6-B6)^2','=(D6-B6)^2','=(E6-B6)^2']];forecast.getRange('I6:K24').fillDown();
forecast.getRange('A6:A24').setNumberFormat('mmm yyyy');forecast.getRange('B6:E24').setNumberFormat('0.00%');forecast.getRange('F6:K24').setNumberFormat('0.0000');
forecast.getRange('A27:D27').values=[['Score summary','One regime','Mixture','Switching']];header(forecast,'A27:D27');
forecast.getRange('A28:A29').values=[['Total log score'],['Mean forecast RMSE']];
forecast.getRange('B28:D29').formulas=[['=SUM(F6:F24)','=SUM(G6:G24)','=SUM(H6:H24)'],['=SQRT(AVERAGE(I6:I24))','=SQRT(AVERAGE(J6:J24))','=SQRT(AVERAGE(K6:K24))']];forecast.getRange('B28:D28').setNumberFormat('0.00');forecast.getRange('B29:D29').setNumberFormat('0.00%');
forecast.getRange('A31').values=[['Higher log scores and lower RMSE are better. Nineteen months is a short validation period.']];forecast.getRange('A1:A33').format.columnWidth=26;forecast.freezePanes.freezeRows(5);

style(sensitivity,'A1:H19');title(sensitivity,'Sensitivity of the fitted states');
sensitivity.getRange('A3').values=[['Hiding an episode removes its returns but retains monthly state transitions through the gap.']];
sensitivity.getRange('A5:H5').values=[['Alternative sample or bound','Observed months','Log likelihood','Lower mean','Higher mean','Lower duration','Higher duration','Higher long-run share']];header(sensitivity,'A5:H5');
sensitivity.getRange('A6:H13').values=r.sensitivity.map(x=>[x.name,x.n,x.fit.ll,x.moments.mean_returns[0],x.moments.mean_returns[1],x.moments.durations[0],x.moments.durations[1],x.moments.stationary[1]]);
sensitivity.getRange('C6:C13').setNumberFormat('0.00');sensitivity.getRange('D6:E13').setNumberFormat('0.00%');sensitivity.getRange('F6:G13').setNumberFormat('0.0');sensitivity.getRange('H6:H13').setNumberFormat('0.0%');
sensitivity.getRange('A15').values=[['Mean returns remain positive. Precise durations are sensitive to individual episodes.']];
sensitivity.getRange('A16').values=[['Likelihoods across different samples are not directly comparable.']];sensitivity.getRange('A1:A19').format.columnWidth=58;sensitivity.getRange('B1:H19').format.columnWidth=16;

wb.recalculate();
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:50},summary:'Final formula error scan'});
console.log(errors.ndjson);
console.log((await wb.inspect({kind:'table',range:'Results!A28:B33',include:'values,formulas',tableMaxRows:6,tableMaxCols:2})).ndjson);
console.log((await wb.inspect({kind:'table',range:"'Forecast checks'!A27:D29",include:'values,formulas',tableMaxRows:3,tableMaxCols:4})).ndjson);
await fs.mkdir(qa,{recursive:true});
for (const [name,range,file] of [['Results','A1:H38','workbook_results.png'],['Monthly returns','A1:I12','workbook_monthly.png'],['Forecast checks','A1:K12','workbook_forecast.png'],['Sensitivity','A1:H16','workbook_sensitivity.png']]){
  const p=await wb.render({sheetName:name,range,scale:1.5,format:'png'});await fs.writeFile(path.join(qa,file),new Uint8Array(await p.arrayBuffer()));
}
const output=await SpreadsheetFile.exportXlsx(wb);await output.save(path.join(root,'Assignment_7_Fund_X_Two_Regime_Review.xlsx'));
console.log('Workbook saved');
