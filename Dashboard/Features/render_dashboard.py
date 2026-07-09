import streamlit as st
import plotly.graph_objects as go
from .fetch_clean_data import fetch_clean_data
from Dashboard.Features.market_structure import (
    extract_market_structure,
    get_swing_zones,
    get_pdh_pdl,
)


def render_dashboard(tickers, interval, period, settings):

    cols = st.columns(2)   # 2 charts per row

    for i, ticker in enumerate(tickers):

        with cols[i % 2]:

            df = fetch_clean_data(ticker, interval, period)

            if df is None:
                st.warning(f"No data: {ticker}")
                continue

            # =====================================================
            # PLOTLY FIGURE
            # =====================================================
            fig = go.Figure()

            # =====================================================
            # CHART TYPE
            # =====================================================
            if settings["show_line_chart"]:
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df['Close'],
                        mode='lines',
                        name='Close',
                        line=dict(width=2),
                        hoverinfo='skip',
                    )
                )
            else:
                fig.add_trace(
                    go.Candlestick(
                        x=df.index,
                        open=df['Open'],
                        high=df['High'],
                        low=df['Low'],
                        close=df['Close'],
                        name='Price',
                        increasing_line_color='lime',
                        decreasing_line_color='red',
                        # suppress hover tooltip — details shown on click below
                        hoverinfo='skip',
                    )
                )

            # =====================================================
            # EMA
            # =====================================================
            if settings["show_ema"]:
                df['EMA9']  = df['Close'].ewm(span=9).mean()
                df['EMA21'] = df['Close'].ewm(span=21).mean()

                fig.add_trace(
                    go.Scatter(
                        x=df.index, y=df['EMA9'],
                        mode='lines', name='EMA 9',
                        line=dict(width=1),
                        hoverinfo='skip',
                    )
                )
                fig.add_trace(
                    go.Scatter(
                        x=df.index, y=df['EMA21'],
                        mode='lines', name='EMA 21',
                        line=dict(width=1),
                        hoverinfo='skip',
                    )
                )

            # =====================================================
            # MARKET STRUCTURE  (swings / supports / resistance / TL)
            # =====================================================
            structure = extract_market_structure(df)

            if settings["show_swings"]:
                fig.add_trace(
                    go.Scatter(
                        x=[df.index[x["index"]] for x in structure["swing_highs"]],
                        y=[x["price"] for x in structure["swing_highs"]],
                        mode='markers',
                        name='Swing Highs',
                        marker=dict(size=7),
                        hoverinfo='skip',
                    )
                )
                fig.add_trace(
                    go.Scatter(
                        x=[df.index[x["index"]] for x in structure["swing_lows"]],
                        y=[x["price"] for x in structure["swing_lows"]],
                        mode='markers',
                        name='Swing Lows',
                        marker=dict(size=7),
                        hoverinfo='skip',
                    )
                )

            if settings["show_supports"]:
                for s in structure["supports"]:
                    fig.add_shape(
                        type="line",
                        x0=df.index[s["index"]], x1=df.index[s["touches"][-1]],
                        y0=s["price"], y1=s["price"],
                        line=dict(dash='dash', width=1)
                    )

            if settings["show_resistance"]:
                for r in structure["resistances"]:
                    fig.add_shape(
                        type="line",
                        x0=df.index[r["index"]], x1=df.index[r["touches"][-1]],
                        y0=r["price"], y1=r["price"],
                        line=dict(dash='dash', width=1)
                    )

            if settings["show_trendlines"]:
                for line in structure["support_trendlines"]:
                    pts    = line["points"]
                    y_vals = [line["slope"] * x + line["intercept"] for x in pts]
                    fig.add_trace(
                        go.Scatter(
                            x=[df.index[x] for x in pts], y=y_vals,
                            mode='lines', name='Support TL',
                            line=dict(dash='dot'),
                            hoverinfo='skip',
                        )
                    )
                for line in structure["resistance_trendlines"]:
                    pts    = line["points"]
                    y_vals = [line["slope"] * x + line["intercept"] for x in pts]
                    fig.add_trace(
                        go.Scatter(
                            x=[df.index[x] for x in pts], y=y_vals,
                            mode='lines', name='Resistance TL',
                            line=dict(dash='dot'),
                            hoverinfo='skip',
                        )
                    )

            # =====================================================
            # SWING ZONES  (via market_structure → Highs_Lows.py)
            # =====================================================
            if settings["show_swing_zones"]:

                swings, zones = get_swing_zones(df)

                HIGH_CLR = "rgba(239,83,80,"   # red
                LOW_CLR  = "rgba(38,166,154,"  # teal

                for z in zones:
                    base_clr = HIGH_CLR if z["type"] == "high" else LOW_CLR
                    fill_a   = "0.07)" if z["broken"] else "0.18)"
                    edge_a   = "0.27)" if z["broken"] else "0.75)"
                    x0, x1   = df.index[z["left"]], df.index[z["right"]]

                    fig.add_shape(
                        type="rect",
                        x0=x0, x1=x1,
                        y0=z["bottom"], y1=z["top"],
                        fillcolor=base_clr + fill_a,
                        line=dict(width=0),
                        layer="below"
                    )
                    fig.add_shape(
                        type="line",
                        x0=x0, x1=x1,
                        y0=z["top"], y1=z["top"],
                        line=dict(color=base_clr + edge_a, width=1)
                    )
                    fig.add_shape(
                        type="line",
                        x0=x0, x1=x1,
                        y0=z["bottom"], y1=z["bottom"],
                        line=dict(color=base_clr + edge_a, width=1)
                    )

                for s in swings:
                    clr = "#ef5350" if s["type"] == "high" else "#26a69a"
                    fig.add_trace(
                        go.Scatter(
                            x=[df.index[s["index"]]],
                            y=[s["price"]],
                            mode="markers+text",
                            marker=dict(symbol="diamond", size=8, color=clr),
                            text=[f"{s['price']:.1f}"],
                            textposition=(
                                "top center" if s["type"] == "high"
                                else "bottom center"
                            ),
                            textfont=dict(size=8, color=clr),
                            showlegend=False,
                            hoverinfo='skip',
                        )
                    )

            # =====================================================
            # PDH / PDL  (via market_structure → Highs_Lows.py)
            # =====================================================
            if settings["show_pdh_pdl"]:

                pdh, pdl = get_pdh_pdl(ticker)

                if pdh is not None:
                    fig.add_hline(
                        y=pdh,
                        line=dict(color="#ffb74d", width=1.2, dash="dash"),
                        annotation_text=f"PDH  {pdh:.2f}",
                        annotation_position="top right",
                        annotation_font=dict(color="#ffb74d", size=9),
                    )
                if pdl is not None:
                    fig.add_hline(
                        y=pdl,
                        line=dict(color="#81d4fa", width=1.2, dash="dash"),
                        annotation_text=f"PDL  {pdl:.2f}",
                        annotation_position="bottom right",
                        annotation_font=dict(color="#81d4fa", size=9),
                    )

            # =====================================================
            # LAYOUT  — no legend, no hover tooltip
            # =====================================================
            latest = round(df['Close'].iloc[-1], 2)

            fig.update_layout(
                title={
                    'text': f"{ticker} | {interval} | {period} | ₹{latest}",
                    'x': 0.02,
                    'xanchor': 'left'
                },
                template="plotly_dark",
                height=420,
                margin=dict(l=10, r=10, t=35, b=10),
                xaxis_rangeslider_visible=False,
                dragmode='pan',

                # ── no floating tooltip on hover ──
                hovermode=False,

                # ── legend hidden (would eat space) ──
                showlegend=False,

                xaxis=dict(
                    showgrid=False,
                    rangebreaks=[
                        dict(bounds=["sat", "mon"]),
                        dict(bounds=[15.5, 9.15], pattern="hour")
                    ]
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor='rgba(255,255,255,0.08)'
                )
            )

            # =====================================================
            # RENDER CHART + CLICK-BASED CANDLE DETAIL
            # =====================================================
            chart_key   = f"chart_{ticker}_{i}"
            detail_slot = st.empty()

            event = st.plotly_chart(
                fig,
                width='stretch',
                config={"displayModeBar": True},
                on_select="rerun",
                key=chart_key,
            )

            # When the user clicks a point, show OHLC detail below the chart
            pts = (event or {}).get("selection", {}).get("points", [])
            if pts:
                pt  = pts[0]
                raw = pt.get("x")
                if raw:
                    # match clicked timestamp to df row
                    try:
                        clicked_ts = str(raw)
                        row = df[df.index.astype(str).str.startswith(clicked_ts[:16])]
                        if not row.empty:
                            r = row.iloc[0]
                            delta = round(r['Close'] - r['Open'], 2)
                            color = "🟢" if delta >= 0 else "🔴"
                            detail_slot.markdown(
                                f"**{ticker}** &nbsp;|&nbsp; `{row.index[0].strftime('%d %b %Y  %H:%M')}`"
                                f"&nbsp;&nbsp; {color} &nbsp;"
                                f"O `{r['Open']:.2f}` &nbsp;"
                                f"H `{r['High']:.2f}` &nbsp;"
                                f"L `{r['Low']:.2f}` &nbsp;"
                                f"C `{r['Close']:.2f}` &nbsp;"
                                f"Δ `{delta:+.2f}`"
                            )
                    except Exception:
                        pass
