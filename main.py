// @version=6
// =============================================================================
// noelnqbot - MNQ Window Reversal Bot
// =============================================================================
// Strategy:
//   Trades at five primary windows (10:00, 10:30, 11:00, 11:30, 12:00 NY)
//   plus two afternoon windows (13:55, 15:00 NY).
//
//   Within each window, three triggers (A, B, C) look for reversal setups.
//   At most ONE trade per window. After a stop-out, the window is done.
//
//   Position size: 5 MNQ.
//   Initial stop: 30 points.
//   No take profit; stop trails based on unrealized PnL.
//
// This script is attached to an MNQ chart at 1-minute timeframe.
// All price logic uses the chart's native timeframe.
// =============================================================================

strategy(
     title = "noelnqbot v1",
     shorttitle = "noelnq",
     overlay = true,
     pyramiding = 0,
     default_qty_type = strategy.fixed,
     default_qty_value = 5,
     initial_capital = 50000,
     currency = currency.USD,
     calc_on_every_tick = false,
     process_orders_on_close = true,
     commission_type = strategy.commission.cash_per_contract,
     commission_value = 0.74,
     slippage = 1
 )

// =============================================================================
// INPUTS - tweak these in TradingView without re-editing code
// =============================================================================

// --- Position sizing ---
contracts = input.int(5, "Contracts (MNQ)", minval=1, maxval=20,
     tooltip="Number of MNQ contracts per trade")

// --- Stop and trail parameters ---
initialStopPts = input.float(30.0, "Initial stop (pts)", minval=1.0, maxval=100.0, group="Stop/Trail")
reduceRiskAtPts = input.float(10.0, "Reduce risk: at +X pts profit...", minval=1.0, group="Stop/Trail")
reduceRiskToPts = input.float(-20.0, "...move stop to Y pts from entry", group="Stop/Trail",
     tooltip="Negative = still at a loss but reduced. E.g. -20 means stop at 20pt loss instead of 30.")
breakevenPlusAtPts = input.float(15.0, "Breakeven+: at +X pts...", minval=1.0, group="Stop/Trail")
breakevenPlusToPts = input.float(5.0, "...move stop to +Y", group="Stop/Trail")
trailBehindPts = input.float(10.0, "After breakeven+, trail Y pts behind current price", minval=1.0, group="Stop/Trail")

// --- Trigger A: pullback to window open ---
trigA_minMovePts = input.float(8.0, "Trigger A: min move from open (pts)", minval=1.0, group="Trigger A: Pullback")
trigA_maxMovePts = input.float(15.0, "Trigger A: max move from open (pts)", minval=1.0, group="Trigger A: Pullback")
trigA_openPricePadding = input.float(1.0, "Trigger A: pullback precision (pts from open)", minval=0.25, group="Trigger A: Pullback",
     tooltip="Pullback must be within this many points of window open to trigger.")

// --- Trigger B: trailing chase past 20 pts ---
trigB_activationPts = input.float(20.0, "Trigger B: activate at move (pts)", minval=10.0, group="Trigger B: Trail Chase")
trigB_trailLoose = input.float(15.0, "Trigger B: initial trail distance (pts)", minval=1.0, group="Trigger B: Trail Chase",
     tooltip="How many pts behind extreme to place the trail when B first activates.")
trigB_trailMedium = input.float(5.0, "Trigger B: medium trail (past +40)", minval=1.0, group="Trigger B: Trail Chase")
trigB_trailTight = input.float(3.0, "Trigger B: tight trail (past +80)", minval=1.0, group="Trigger B: Trail Chase")
trigB_mediumAtPts = input.float(40.0, "Trigger B: switch to medium at move (pts)", minval=20.0, group="Trigger B: Trail Chase")
trigB_tightAtPts = input.float(80.0, "Trigger B: switch to tight at move (pts)", minval=40.0, group="Trigger B: Trail Chase")

// --- Trigger C: wick reversal fallback ---
trigC_minMovePts = input.float(5.0, "Trigger C: min prior move (pts)", minval=1.0, group="Trigger C: Wick Reversal")
trigC_minWickPts = input.float(3.0, "Trigger C: min wick size (pts)", minval=0.5, group="Trigger C: Wick Reversal")
trigC_fallbackMinutesStart = input.int(4, "Trigger C: start minute of fallback window", minval=1, group="Trigger C: Wick Reversal")
trigC_fallbackMinutesEnd = input.int(5, "Trigger C: end minute of fallback window", minval=1, group="Trigger C: Wick Reversal",
     tooltip="E.g. if start=4 and end=5, Trigger C can fire at 10:04 or 10:05 bars.")

// --- Windows ---
enableMorningWindows = input.bool(true, "Enable morning windows (10:00-12:15)", group="Windows")
enableAfternoonWindows = input.bool(true, "Enable afternoon windows (13:55, 15:00)", group="Windows")

// --- Alerts ---
enableAlerts = input.bool(true, "Enable webhook alerts", group="Alerts",
     tooltip="Turn off to test without flooding your Telegram.")

// =============================================================================
// TIME / SESSION LOGIC
// =============================================================================
// TradingView serves NY time for MNQ charts by default on most setups, but to
// be safe we explicitly convert to America/New_York. If your chart is in a
// different timezone, the logic still works because we check time-of-day
// against NY.

nyHour = hour(time, "America/New_York")
nyMinute = minute(time, "America/New_York")
currentMinuteOfDay = nyHour * 60 + nyMinute

// Is this bar in RTH at all?
inRTH = (currentMinuteOfDay >= 570 and currentMinuteOfDay < 960)  // 09:30 to 16:00

// Window open times (minute-of-day in NY):
// Morning: 600 (10:00), 630 (10:30), 660 (11:00), 690 (11:30), 720 (12:00)
// Afternoon: 835 (13:55), 900 (15:00)
// A "window" runs from its open until the next window opens, OR until 12:15 (morning) / end-of-RTH (afternoon).

windowOpenMinutes = array.new<int>()
windowEndMinutes = array.new<int>()

if enableMorningWindows
    array.push(windowOpenMinutes, 600)   // 10:00
    array.push(windowEndMinutes, 630)
    array.push(windowOpenMinutes, 630)   // 10:30
    array.push(windowEndMinutes, 660)
    array.push(windowOpenMinutes, 660)   // 11:00
    array.push(windowEndMinutes, 690)
    array.push(windowOpenMinutes, 690)   // 11:30
    array.push(windowEndMinutes, 720)
    array.push(windowOpenMinutes, 720)   // 12:00
    array.push(windowEndMinutes, 735)    // until 12:15

if enableAfternoonWindows
    array.push(windowOpenMinutes, 835)   // 13:55
    array.push(windowEndMinutes, 880)    // until 14:40
    array.push(windowOpenMinutes, 900)   // 15:00
    array.push(windowEndMinutes, 960)    // until 16:00

// Which window am I in right now? Returns index into the arrays, or -1.
getCurrentWindowIdx() =>
    result = -1
    if inRTH
        for i = 0 to array.size(windowOpenMinutes) - 1
            openM = array.get(windowOpenMinutes, i)
            endM = array.get(windowEndMinutes, i)
            if currentMinuteOfDay >= openM and currentMinuteOfDay < endM
                result := i
                break
    result

currentWindowIdx = getCurrentWindowIdx()
inAnyWindow = currentWindowIdx >= 0
windowOpenM = inAnyWindow ? array.get(windowOpenMinutes, currentWindowIdx) : -1
minutesSinceWindowOpen = inAnyWindow ? (currentMinuteOfDay - windowOpenM) : -1
isWindowOpenBar = inAnyWindow and minutesSinceWindowOpen == 0

// =============================================================================
// PER-WINDOW STATE
// =============================================================================
// State that resets at each window open and persists through the window:
//   - windowOpenPrice: the open of the first bar in the window
//   - extremeHigh / extremeLow: running H/L from window open
//   - triggerA_Fired, triggerB_Fired, triggerC_Fired: has a trigger activated this window?
//   - windowStoppedOut: did we take and lose a trade in this window? If yes, no more trades this window.
//   - triggerB_Armed: has the 20pt threshold been crossed (trigger B is now looking for a reversal)?
//   - triggerB_ExtremePrice: the running high/low used for B's trailing level
//   - triggerB_IsUpMove: direction of the move B is trailing against

var float windowOpenPrice = na
var float extremeHigh = na
var float extremeLow = na
var bool triggerA_Fired = false
var bool triggerB_Fired = false
var bool triggerC_Fired = false
var bool windowStoppedOut = false
var bool triggerB_Armed = false
var bool triggerB_IsUpMove = na
var float triggerB_ExtremePrice = na
var int currentWindowIdxVar = -1

// Reset state at window open
if isWindowOpenBar and currentWindowIdx != currentWindowIdxVar
    windowOpenPrice := open
    extremeHigh := high
    extremeLow := low
    triggerA_Fired := false
    triggerB_Fired := false
    triggerC_Fired := false
    windowStoppedOut := false
    triggerB_Armed := false
    triggerB_IsUpMove := na
    triggerB_ExtremePrice := na
    currentWindowIdxVar := currentWindowIdx

// Update extremes within the window
if inAnyWindow and not isWindowOpenBar
    extremeHigh := math.max(extremeHigh, high)
    extremeLow := math.min(extremeLow, low)

// =============================================================================
// DAILY LEVELS (for context in alerts)
// =============================================================================
// Yesterday's RTH high/low, prior close, overnight high/low, etc.
// These are informational only - bot doesn't use them as filters.

var float ydayRthHigh = na
var float ydayRthLow = na
var float priorClose = na
var float preMarketHigh = na
var float preMarketLow = na
var float midnightOpen = na
var float eightThirtyOpen = na

// Track today's RTH range
var float todayRthHigh = na
var float todayRthLow = na

isNewSession = ta.change(time("D")) != 0
if isNewSession
    // Roll yesterday's values
    ydayRthHigh := todayRthHigh
    ydayRthLow := todayRthLow
    priorClose := close[1]
    // Reset today
    todayRthHigh := na
    todayRthLow := na
    preMarketHigh := na
    preMarketLow := na

// Capture midnight open (first bar of the day)
if isNewSession
    midnightOpen := open

// Track pre-market (04:00 to 09:30)
if nyHour >= 4 and currentMinuteOfDay < 570
    preMarketHigh := na(preMarketHigh) ? high : math.max(preMarketHigh, high)
    preMarketLow := na(preMarketLow) ? low : math.min(preMarketLow, low)

// Capture 8:30 open
if nyHour == 8 and nyMinute == 30
    eightThirtyOpen := open

// Track today RTH
if inRTH
    todayRthHigh := na(todayRthHigh) ? high : math.max(todayRthHigh, high)
    todayRthLow := na(todayRthLow) ? low : math.min(todayRthLow, low)

// =============================================================================
// TRIGGER DETECTION
// =============================================================================
// Runs on each bar close within a window.
// Key design: a trigger only fires if it's the FIRST eligible setup in the window.
// So we check in order A -> B -> C, and once any fires, we stop checking.

// Helper: current move from window open (signed)
moveFromOpen = inAnyWindow ? (close - windowOpenPrice) : 0.0
absMoveFromOpen = math.abs(moveFromOpen)

// Direction of current price movement at this bar (up or down vs prior bar close)
priceMovingUp = close > close[1]
priceMovingDown = close < close[1]

// -----------------------------------------------------------------------------
// Trigger A: pullback to window open after 8-15 pt move
// -----------------------------------------------------------------------------
// Fires when:
//   - Price moved 8-15 pts from open at some point during this window
//   - Price has now returned to within trigA_openPricePadding of the open
//   - We're not the first bar of the window
//   - No trigger has fired yet this window
//   - Window not stopped out
//
// Entry direction: "same direction price is presently moving" (per the user's rule).
// So if price pulled back from an up-move and is now moving DOWN through the open,
// we enter SHORT. If price pulled back from a down-move and is now moving UP through
// the open, we enter LONG.

hadValidAMove = inAnyWindow and ((extremeHigh - windowOpenPrice) >= trigA_minMovePts and (extremeHigh - windowOpenPrice) <= trigA_maxMovePts) or ((windowOpenPrice - extremeLow) >= trigA_minMovePts and (windowOpenPrice - extremeLow) <= trigA_maxMovePts)

// Distance from open right now
distFromOpen = math.abs(close - windowOpenPrice)
atWindowOpen = distFromOpen <= trigA_openPricePadding

triggerA_Long = inAnyWindow and not isWindowOpenBar and not triggerA_Fired and not triggerB_Fired and not triggerC_Fired and not windowStoppedOut and strategy.position_size == 0 and hadValidAMove and atWindowOpen and priceMovingUp

triggerA_Short = inAnyWindow and not isWindowOpenBar and not triggerA_Fired and not triggerB_Fired and not triggerC_Fired and not windowStoppedOut and strategy.position_size == 0 and hadValidAMove and atWindowOpen and priceMovingDown

// -----------------------------------------------------------------------------
// Trigger B: trailing chase past 20 pts
// -----------------------------------------------------------------------------
// Arms when price moves 20+ pts from open (up or down).
// Once armed, it tracks the extreme and places a conceptual trailing level.
// Fires when price crosses back through the trailing level (reversal confirmed).
//
// Entry direction: opposite the move.

// Arm logic: set armed flag and direction on the bar that first breaches +/- 20
if inAnyWindow and not triggerB_Armed and not triggerA_Fired and not triggerC_Fired and not windowStoppedOut
    if (extremeHigh - windowOpenPrice) >= trigB_activationPts
        triggerB_Armed := true
        triggerB_IsUpMove := true
        triggerB_ExtremePrice := extremeHigh
    else if (windowOpenPrice - extremeLow) >= trigB_activationPts
        triggerB_Armed := true
        triggerB_IsUpMove := false
        triggerB_ExtremePrice := extremeLow

// Update extreme as move extends
if triggerB_Armed
    if triggerB_IsUpMove and high > triggerB_ExtremePrice
        triggerB_ExtremePrice := high
    if not triggerB_IsUpMove and low < triggerB_ExtremePrice
        triggerB_ExtremePrice := low

// Compute current trail distance based on how far the move extended
trigB_currentTrailDist = 0.0
if triggerB_Armed
    moveExtent = triggerB_IsUpMove ? (triggerB_ExtremePrice - windowOpenPrice) : (windowOpenPrice - triggerB_ExtremePrice)
    if moveExtent >= trigB_tightAtPts
        trigB_currentTrailDist := trigB_trailTight
    else if moveExtent >= trigB_mediumAtPts
        trigB_currentTrailDist := trigB_trailMedium
    else
        trigB_currentTrailDist := trigB_trailLoose

// Trigger level
trigB_trailLevel = triggerB_Armed ? (triggerB_IsUpMove ? (triggerB_ExtremePrice - trigB_currentTrailDist) : (triggerB_ExtremePrice + trigB_currentTrailDist)) : na

// Fire: price crosses back through the trail level
triggerB_Long = triggerB_Armed and not triggerB_Fired and not triggerA_Fired and not triggerC_Fired and not windowStoppedOut and strategy.position_size == 0 and not triggerB_IsUpMove and close >= trigB_trailLevel

triggerB_Short = triggerB_Armed and not triggerB_Fired and not triggerA_Fired and not triggerC_Fired and not windowStoppedOut and strategy.position_size == 0 and triggerB_IsUpMove and close <= trigB_trailLevel

// -----------------------------------------------------------------------------
// Trigger C: wick reversal fallback at :04-:05
// -----------------------------------------------------------------------------
// Only eligible if no prior trigger fired AND the :04-:05 bars of the window.
// Requires 5+ pt prior move, 3+ pt wick against, opposite-color close.

inFallbackWindow = inAnyWindow and minutesSinceWindowOpen >= trigC_fallbackMinutesStart and minutesSinceWindowOpen <= trigC_fallbackMinutesEnd

upperWick = high - math.max(open, close)
lowerWick = math.min(open, close) - low
barIsRed = close < open
barIsGreen = close > open

priorMoveUp = (extremeHigh - windowOpenPrice) >= trigC_minMovePts
priorMoveDown = (windowOpenPrice - extremeLow) >= trigC_minMovePts

triggerC_Short = inFallbackWindow and not triggerA_Fired and not triggerB_Fired and not triggerC_Fired and not windowStoppedOut and strategy.position_size == 0 and priorMoveUp and upperWick >= trigC_minWickPts and barIsRed

triggerC_Long = inFallbackWindow and not triggerA_Fired and not triggerB_Fired and not triggerC_Fired and not windowStoppedOut and strategy.position_size == 0 and priorMoveDown and lowerWick >= trigC_minWickPts and barIsGreen

// =============================================================================
// ENTRIES
// =============================================================================

// Track which trigger fired for alerting
var string activeTrigger = ""

if triggerA_Long
    strategy.entry("A_Long", strategy.long, qty=contracts, comment="A_Long")
    triggerA_Fired := true
    activeTrigger := "A_Long"

if triggerA_Short
    strategy.entry("A_Short", strategy.short, qty=contracts, comment="A_Short")
    triggerA_Fired := true
    activeTrigger := "A_Short"

if triggerB_Long
    strategy.entry("B_Long", strategy.long, qty=contracts, comment="B_Long")
    triggerB_Fired := true
    activeTrigger := "B_Long"

if triggerB_Short
    strategy.entry("B_Short", strategy.short, qty=contracts, comment="B_Short")
    triggerB_Fired := true
    activeTrigger := "B_Short"

if triggerC_Long
    strategy.entry("C_Long", strategy.long, qty=contracts, comment="C_Long")
    triggerC_Fired := true
    activeTrigger := "C_Long"

if triggerC_Short
    strategy.entry("C_Short", strategy.short, qty=contracts, comment="C_Short")
    triggerC_Fired := true
    activeTrigger := "C_Short"

// =============================================================================
// STOP AND TRAIL MANAGEMENT
// =============================================================================
// On every bar while in position:
//   - If unrealized PnL >= +10 pts, stop moves to -20 (from initial -30)
//   - If >= +15 pts, stop moves to +5
//   - Past +15, stop trails 10 pts behind current price

var float currentStopPrice = na
var float entryPriceVar = na

// On entry, set the initial stop
if strategy.position_size != 0 and strategy.position_size[1] == 0
    entryPriceVar := strategy.position_avg_price
    currentStopPrice := strategy.position_size > 0 ? (entryPriceVar - initialStopPts) : (entryPriceVar + initialStopPts)

// Update trailing stop each bar
if strategy.position_size != 0
    isLong = strategy.position_size > 0
    unrealizedPts = isLong ? (close - entryPriceVar) : (entryPriceVar - close)

    proposedStop = currentStopPrice  // default: no change

    if unrealizedPts >= breakevenPlusAtPts
        // Trail 10 pts behind current price
        trailStop = isLong ? (close - trailBehindPts) : (close + trailBehindPts)
        // But never looser than the breakeven-plus level
        bePlusStop = isLong ? (entryPriceVar + breakevenPlusToPts) : (entryPriceVar - breakevenPlusToPts)
        candidate = isLong ? math.max(trailStop, bePlusStop) : math.min(trailStop, bePlusStop)
        proposedStop := isLong ? math.max(currentStopPrice, candidate) : math.min(currentStopPrice, candidate)
    else if unrealizedPts >= reduceRiskAtPts
        reducedStop = isLong ? (entryPriceVar + reduceRiskToPts) : (entryPriceVar - reduceRiskToPts)
        proposedStop := isLong ? math.max(currentStopPrice, reducedStop) : math.min(currentStopPrice, reducedStop)

    currentStopPrice := proposedStop

    // Submit stop order
    strategy.exit("Stop", from_entry=isLong ? "A_Long" : "A_Short", stop=currentStopPrice)
    // Do the same for the other entry IDs (pine requires explicit from_entry)
    strategy.exit("StopB", from_entry=isLong ? "B_Long" : "B_Short", stop=currentStopPrice)
    strategy.exit("StopC", from_entry=isLong ? "C_Long" : "C_Short", stop=currentStopPrice)

// Mark the window as stopped-out when a position closes via stop
if strategy.position_size == 0 and strategy.position_size[1] != 0
    windowStoppedOut := true
    currentStopPrice := na
    entryPriceVar := na

// =============================================================================
// VISUAL AIDES ON CHART
// =============================================================================

// Plot window open price as horizontal ray during the window
plot(inAnyWindow ? windowOpenPrice : na, "Window Open", color=color.new(color.yellow, 40), linewidth=1)
plot(triggerB_Armed and not triggerB_Fired ? trigB_trailLevel : na, "B Trail", color=color.new(color.orange, 30), linewidth=2, style=plot.style_circles)
plot(strategy.position_size != 0 ? currentStopPrice : na, "Stop", color=color.new(color.red, 0), linewidth=2, style=plot.style_linebr)

bgcolor(inAnyWindow ? color.new(color.blue, 93) : na, title="Window")

// =============================================================================
// WEBHOOK ALERTS
// =============================================================================
// TradingView's alertcondition() fires on these events, with a JSON payload.
// The Python relay parses the JSON and forwards to Telegram.

// Entry alert
onEntry = (triggerA_Long or triggerA_Short or triggerB_Long or triggerB_Short or triggerC_Long or triggerC_Short)

if enableAlerts and onEntry
    windowLabel = switch currentWindowIdx
        0 => "10:00"
        1 => "10:30"
        2 => "11:00"
        3 => "11:30"
        4 => "12:00"
        5 => "13:55"
        6 => "15:00"
        => "unknown"

    side = (triggerA_Long or triggerB_Long or triggerC_Long) ? "LONG" : "SHORT"
    trig = triggerA_Long or triggerA_Short ? "A" : triggerB_Long or triggerB_Short ? "B" : "C"

    jsonMsg = '{"event":"entry","window":"' + windowLabel + '","trigger":"' + trig + '","side":"' + side + '","price":' + str.tostring(close, "#.##") + ',"move_from_open":' + str.tostring(moveFromOpen, "#.##") + ',"extreme_high":' + str.tostring(extremeHigh, "#.##") + ',"extreme_low":' + str.tostring(extremeLow, "#.##") + ',"yday_high":' + str.tostring(ydayRthHigh, "#.##") + ',"yday_low":' + str.tostring(ydayRthLow, "#.##") + ',"prior_close":' + str.tostring(priorClose, "#.##") + ',"premkt_high":' + str.tostring(preMarketHigh, "#.##") + ',"premkt_low":' + str.tostring(preMarketLow, "#.##") + ',"midnight_open":' + str.tostring(midnightOpen, "#.##") + ',"eight_thirty_open":' + str.tostring(eightThirtyOpen, "#.##") + '}'

    alert(jsonMsg, alert.freq_once_per_bar_close)

// Exit alert (when position goes from non-zero to zero, except on same bar as entry)
onExit = strategy.position_size == 0 and strategy.position_size[1] != 0

if enableAlerts and onExit
    // Find the most recent closed trade for exit details
    exitSide = strategy.position_size[1] > 0 ? "CLOSED_LONG" : "CLOSED_SHORT"
    pnlPts = strategy.closedtrades.profit(strategy.closedtrades - 1) / (syminfo.pointvalue * contracts)
    pnlDollars = strategy.closedtrades.profit(strategy.closedtrades - 1)

    jsonMsg = '{"event":"exit","side":"' + exitSide + '","price":' + str.tostring(close, "#.##") + ',"pnl_pts":' + str.tostring(pnlPts, "#.##") + ',"pnl_dollars":' + str.tostring(pnlDollars, "#.##") + '}'

    alert(jsonMsg, alert.freq_once_per_bar_close)
