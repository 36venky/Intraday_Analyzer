import streamlit as st
import plotly.graph_objects as go
from .fetch_clean_data import fetch_clean_data
from Features.market_structure import extract_market_structure

def render_dashboard(tickers, interval, period, settings):

    cols = st.columns(2)   # 2 charts per row

    for i, ticker in enumerate(tickers):

        with cols[i % 2]:

            df = fetch_clean_data(
                ticker,
                interval,
                period
            )

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

                        line=dict(width=2)
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

                        decreasing_line_color='red'
                    )
                )

            if settings["show_ema"]:
                # =====================================================
                # EMA CALCULATION
                # =====================================================
                df['EMA9'] = df['Close'].ewm(span=9).mean()
                df['EMA21'] = df['Close'].ewm(span=21).mean()

                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df['EMA9'],
                        mode='lines',
                        name='EMA 9',
                        line=dict(width=1)
                    )
                )

                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df['EMA21'],
                        mode='lines',
                        name='EMA 21',
                        line=dict(width=1)
                    )
                )
            # =====================================================
            # SWING POINTS
            # =====================================================

            structure = extract_market_structure(df)

            if settings["show_swings"]:

                swing_highs = structure["swing_highs"]
                swing_lows = structure["swing_lows"]

                fig.add_trace(
                    go.Scatter(
                        x=[df.index[x["index"]] for x in swing_highs],
                        y=[x["price"] for x in swing_highs],
                        mode='markers',
                        name='Swing Highs',
                        marker=dict(size=7)
                    )
                )

                fig.add_trace(
                    go.Scatter(
                        x=[df.index[x["index"]] for x in swing_lows],
                        y=[x["price"] for x in swing_lows],
                        mode='markers',
                        name='Swing Lows',
                        marker=dict(size=7)
                    )
                )
            # =====================================================
            # SUPPORTS
            # =====================================================
            if settings["show_supports"]:

                for s in structure["supports"]:

                    start = s["index"]
                    end = s["touches"][-1]

                    level = s["price"]

                    fig.add_shape(
                        type="line",
                        x0=df.index[start],
                        x1=df.index[end],
                        y0=level,
                        y1=level,
                        line=dict(
                            dash='dash',
                            width=1
                        )
                    )
            # =====================================================
            # RESISTANCE
            # =====================================================
            if settings["show_resistance"]:

                for r in structure["resistances"]:

                    start = r["index"]
                    end = r["touches"][-1]

                    level = r["price"]

                    fig.add_shape(
                        type="line",
                        x0=df.index[start],
                        x1=df.index[end],
                        y0=level,
                        y1=level,
                        line=dict(
                            dash='dash',
                            width=1
                        )
                    )
            # =====================================================
            # TRENDLINES
            # =====================================================
            if settings["show_trendlines"]:

                # SUPPORT TRENDLINES
                for line in structure["support_trendlines"]:

                    pts = line["points"]

                    x_vals = pts

                    y_vals = [
                        line["slope"] * x + line["intercept"]
                        for x in x_vals
                    ]

                    fig.add_trace(
                        go.Scatter(
                            x=[df.index[x] for x in x_vals],
                            y=y_vals,
                            mode='lines',
                            name='Support TL',
                            line=dict(dash='dot')
                        )
                    )

                # RESISTANCE TRENDLINES
                for line in structure["resistance_trendlines"]:

                    pts = line["points"]

                    x_vals = pts

                    y_vals = [
                        line["slope"] * x + line["intercept"]
                        for x in x_vals
                    ]

                    fig.add_trace(
                        go.Scatter(
                            x=[df.index[x] for x in x_vals],
                            y=y_vals,
                            mode='lines',
                            name='Resistance TL',
                            line=dict(dash='dot')
                        )
                    )
            
            # =====================================================
            # LAYOUT
            # =====================================================
            
            latest = round(df['Close'].iloc[-1], 2)

            fig.update_layout(

                title={
                    'text':
                        f"{ticker} | {interval} | {period} | ₹{latest}",
                    'x': 0.02,
                    'xanchor': 'left'
                },

                template="plotly_dark",

                height=420,

                margin=dict(
                    l=10,
                    r=10,
                    t=35,
                    b=10
                ),

                xaxis_rangeslider_visible=False,

                dragmode='pan',

                hovermode='x unified',

                legend=dict(
                    orientation='h',
                    yanchor='bottom',
                    y=1.02,
                    xanchor='right',
                    x=1
                ),

                xaxis=dict(

                    showgrid=False,

                    rangebreaks=[

                        dict(bounds=["sat", "mon"]),

                        dict(
                            bounds=[15.5, 9.15],
                            pattern="hour"
                        )
                    ]
                ),

                yaxis=dict(
                    showgrid=True,
                    gridcolor='rgba(255,255,255,0.08)'
                )
            )

            # =====================================================
            # RENDER
            # =====================================================
            st.plotly_chart(
                fig,
                width='stretch',
                config={
                    #"scrollZoom": True,
                    "displayModeBar": True
                }
            )