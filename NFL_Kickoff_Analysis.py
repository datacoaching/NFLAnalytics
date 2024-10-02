import streamlit as st # Streamlit package used for visualization and data app development
import nfl_data_py as nfl  # NFL data retrieval and analysis (via https://pypi.org/project/nfl-data-py/)
import pandas as pd  # Data manipulation and analysis
import duckdb # Used to write SQL inside Python script
import plotly.express as px # Used to create Python visualizations
import plotly.graph_objects as go # Used to create Python visualizations
# pip install streamlit-autorefresh
from streamlit_autorefresh import st_autorefresh

# Refresh every 20 minutes
st_autorefresh(interval=1200000, key="datarefresh")

# Create a list of seasons. Add 2025 next year
years = [2020, 2021, 2022, 2023, 2024]

# Selects the latest year from the years list
max_year = max(years)

# Adding a cache and function to make the user experience better when interacting with filters
@st.cache_data
def load_game_logs():
    
    # Create an empty list to store DataFrames for each year
    df_game_log_list = []
    
    # Loop through each year, read the data, and append it to the list
    for year in years:
        url = f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{year}.csv.gz'
        
        # Read the data for the given year
        df_game_log_year = pd.read_csv(url, compression='gzip', low_memory=False)
    
        # Filter for only 'kickoff' play types
        df_game_log_year = df_game_log_year[df_game_log_year['play_type'] == 'kickoff']
    
        # Retain columns that have relevance to kickoffs
        df_game_log_year = df_game_log_year[['season','game_id','drive','series','series_result','fixed_drive_result','desc','weather','roof','surface',
                                             'temp','wind','kicker_player_id','kickoff_returner_player_id','penalty','return_team','return_yards',
                                           'penalty_player_id','penalty_type','penalty_yards','end_yard_line','kickoff_inside_twenty','kickoff_in_endzone',
                                             'kickoff_out_of_bounds','kickoff_downed','kickoff_fair_catch','kick_distance','fumble_lost','drive_start_yard_line',
                                             'touchdown','defteam','play_type','play_deleted','solo_tackle_1_player_id','posteam_type','penalty_team','game_half',
                                             'own_kickoff_recovery','game_seconds_remaining','half_seconds_remaining']]
        
        # Append the filtered DataFrame to the list
        df_game_log_list.append(df_game_log_year)
    
    # Concatenate all the DataFrames for each year into a single DataFrame
    #df_game_log = pd.concat(df_game_log_list)
    return pd.concat(df_game_log_list)

# Load the cached game logs DataFrame
df_game_log = load_game_logs()

# Save NFL players and teams to dataframe
df_players = nfl.import_seasonal_rosters(years) # Import NFL rosters for each year requested
df_teams = nfl.import_team_desc() # Import NFL team information

st.title ('NFL Kickoff Analysis - 2024 Rule Changes')

# --------start filter pane -------------
# Sidebar Filters
st.sidebar.header('Filter Options')

# Minutes remaining in game slider
minutes_remaining_game = st.sidebar.slider('Minutes Remaining in Game', 0, 60, (0, 60))

# Minutes remaining in half slider
minutes_remaining_half = st.sidebar.slider('Minutes Remaining in Half', 0, 30, (0, 30))

# Return type dropdown
return_type = st.sidebar.selectbox('Return Type', ['Select All','Touchback', 'Return'])

# Roof type dropdown
roof_type = st.sidebar.selectbox('Roof Type', ['Select All','closed', 'open', 'outdoors', 'dome'])

# -------end filter pane-----------------

# -------begin sql queries for data prep -----------------------

# Use SQL to create main kickoff data set
kickoffs = duckdb.sql(f"""
                         select a.season,
                                a.game_id,
                                a.drive,
                                a.series,
                                a.series_result,
                                a.fixed_drive_result,
                                a.desc,
                                a.weather,
                                a.roof,
                                a.surface,
                                a.temp,
                                a.wind,
                                a.kicker_player_id,
                                a.kickoff_returner_player_id,
                                a.defteam as kicking_team,
                                c.team_name as kicking_team_name,
                                a.return_team,
                                b.team_name as return_team_name,
                                case
                                  when a.posteam_type='home' then 'Home'
                                  when a.posteam_type='away' then 'Away'
                                end as return_team_location,
                                'https://a.espncdn.com/combiner/i?img=/i/teamlogos/nfl/500/' || a.return_team || '.png&h=200&w=200' as team_logo_espn,
                                a.end_yard_line,
                                a.kickoff_inside_twenty,
                                a.kickoff_in_endzone,
                                a.kickoff_out_of_bounds,
                                a.kickoff_downed,
                                a.kickoff_fair_catch,
                                a.kick_distance,
                                case
                                  when lower(a.desc) like '%injur%' then 1 else 0
                                end as injury,
                                a.fumble_lost,
                                a.drive_start_yard_line,
                                a.touchdown,
                                case
                                  when touchdown=1 then 100
                            	  when a.drive_start_yard_line not like '%' || return_team || '%' then 50 + (50 - cast(replace(a.drive_start_yard_line,defteam||' ','') as float))
                            	  else cast(replace(a.drive_start_yard_line,return_team||' ','') as float)
                                end as yardline_100,
                                case
                                  when d.position='K' then 1 else 0 
                                end as solo_tackle_by_kicker,
                                a.penalty_team,
                                case
                                  when a.return_team=a.penalty_team and a.penalty=1 then 'Receiving Team'
                                  when a.return_team<>a.penalty_team and a.penalty=1 then 'Kicking Team'
                                end as penalty_by_team,
                                a.penalty,
                                a.penalty_player_id,
                                a.penalty_type,
                                coalesce(a.penalty_yards,0) as penalty_yards,
                                case
                                  when a.drive=min(a.drive) over(partition by a.season,a.game_id,a.game_half) then 1
                                  else 0
                                end as first_drive_flag,
                                case
                                  when a.desc like '%onside%' then 1 else 0 
                                end as onside_kick,
                                case
                                  when a.desc like '%onside%' and own_kickoff_recovery=1 then 1
                                  else 0
                                end as onside_kick_successful,
                                game_seconds_remaining,
                                half_seconds_remaining
                                
                         from df_game_log a inner join
                              df_teams b on a.return_team = b.team_abbr inner join
                              df_teams c on a.defteam = c.team_abbr left join
                              df_players d on a.solo_tackle_1_player_id=d.player_id and
                                              a.season = d.season
                            
                         where a.play_type='kickoff' and
                               a.play_deleted=0 and
                               a.return_team is not null and
                               game_seconds_remaining/60.0 BETWEEN {minutes_remaining_game[0]} AND {minutes_remaining_game[1]} and
                               half_seconds_remaining/60.0 BETWEEN {minutes_remaining_half[0]} AND {minutes_remaining_half[1]} and
                               case
                                 when '{roof_type}' = 'Select All' then true
                                 when roof = '{roof_type}' then true
                                 else false
                               end = true and
                               case 
                                 when '{return_type}' = 'Select All' then true
                                 when '{return_type}' = 'Touchback' and kickoff_returner_player_id is null then true
                                 when '{return_type}' = 'Return' and kickoff_returner_player_id is not null then true
                                 else false
                               end = true
                         """).df()

# Use SQL to summarize/aggregate main kickoff data set, kickoffs, at the season level
kickoffs_agg = duckdb.sql("""select 
                                season,
                                count(*) as number_kickoffs,
                                avg(yardline_100) as avg_starting_position,
                                avg(case when kickoff_returner_player_id is not null and penalty=0 then yardline_100 end) as avg_starting_position_returns,
                                avg(case when kickoff_returner_player_id is null and penalty=0 then yardline_100 end) as avg_starting_position_touchbacks,
                                sum(case when touchdown=1 then 1 else 0 end)/(count(*)*1.0) as touchdown_return_rate,
                                sum(case when fixed_drive_result in ('Field goal','Touchdown') then 1 else 0 end)/(count(*)*1.0) as scoring_rate_on_drives_following_kickoffs,
                                sum(case when fixed_drive_result in ('Touchdown') then 1 else 0 end)/(count(*)*1.0) as td_rate_on_drives_following_kickoffs,
                                sum(case when fixed_drive_result in ('Field goal') then 1 else 0 end)/(count(*)*1.0) as fg_rate_on_drives_following_kickoffs,
                                sum(case when fixed_drive_result in ('Field goal','Touchdown') and kickoff_returner_player_id is not null then 1 else 0 end)/sum(case when kickoff_returner_player_id is not null then 1 else 0 end) as scoring_rate_on_drives_following_returns,
                                sum(case when fixed_drive_result in ('Field goal','Touchdown') and kickoff_returner_player_id is null then 1 else 0 end)/sum(case when kickoff_returner_player_id is null then 1 else 0 end) as scoring_rate_on_drives_following_touchbacks,
                                sum(case when fixed_drive_result in ('Field goal','Touchdown') and first_drive_flag = 1 then 1 else 0 end)/(sum(first_drive_flag)*1.0) as scoring_rate_on_first_drives_of_half,
                                sum(injury)/(count(*)*1.0) as injury_rate,
                                sum(injury) as injuries,
                                sum(case when kickoff_returner_player_id is not null then 1 else 0 end)/(count(*)*1.0) as return_rate,
                                sum(penalty) as penalties,
                                sum(penalty)/(count(*)*1.0) as penalty_rate,
                                count(*)/count(distinct game_id) as drives_after_kickoff_per_game
                                
                                from
                                kickoffs
                                
                                group by
                                season""").df()

# Use SQL to summarize/aggregate main kickoff data set, kickoffs, at the team level
kickoffs_team_agg = duckdb.sql("""select 
                                return_team_name,
                                team_logo_espn as url,
                                count(*) as number_kickoffs,
                                avg(yardline_100) as avg_starting_position,
                                avg(case when kickoff_returner_player_id is not null and penalty=0 then yardline_100 end) as avg_starting_position_returns,
                                avg(case when kickoff_returner_player_id is null and penalty=0 then yardline_100 end) as avg_starting_position_touchbacks,
                                sum(case when touchdown=1 then 1 else 0 end)/(count(*)*1.0) as touchdown_return_rate,
                                sum(case when fixed_drive_result in ('Field goal','Touchdown') then 1 else 0 end)/(count(*)*1.0) as scoring_rate_on_drives_following_kickoffs,
                                sum(case when fixed_drive_result in ('Field goal','Touchdown') and kickoff_returner_player_id is not null then 1 else 0 end)/sum(case when kickoff_returner_player_id is not null then 1 else 0 end) as scoring_rate_on_drives_following_returns,
                                sum(case when fixed_drive_result in ('Field goal','Touchdown') and kickoff_returner_player_id is null then 1 else 0 end)/sum(case when kickoff_returner_player_id is null then 1 else 0 end) as scoring_rate_on_drives_following_touchbacks,
                                sum(case when fixed_drive_result in ('Field goal','Touchdown') and first_drive_flag = 1 then 1 else 0 end)/(sum(first_drive_flag)*1.0) as scoring_rate_on_first_drives_of_half,
                                sum(injury)/(count(*)*1.0) as injury_rate,
                                sum(injury) as injuries,
                                sum(case when kickoff_returner_player_id is not null then 1 else 0 end)/(count(*)*1.0) as return_rate,
                                sum(penalty) as penalties,
                                sum(penalty)/(count(*)*1.0) as penalty_rate,
                                count(*)/count(distinct game_id) as drives_after_kickoff_per_game
                                
                                from
                                kickoffs a inner join
                                (select max(season) as max_season
                                   from kickoffs) b on a.season = b.max_season
                                
                                group by
                                return_team_name,
                                team_logo_espn""").df()

# Use SQL to summarize/aggregate main kickoff data set, kickoffs, at the season and penalty level
penalty_agg = duckdb.sql("""select 
                                season,
                                penalty_type,
                                sum(penalty)/max(kickoffs_per_season) as penalty_rate
                                
                                from
                                (select season, 
                                        penalty_type,
                                        penalty,
                                        count(*) over(partition by season) as kickoffs_per_season

                                  from kickoffs
                                )
                                
                                group by
                                season,
                                penalty_type
                            """).df()

# -----------------end sql queries for data prep -----------------

# ---------------- Team Scatter Plot ----------------------------

st.header(f"Scoring Rates Following Kickoffs by Team: {max_year}", divider='gray')

''

# Define values that will map to the x axis, y axis, and team logos
y = kickoffs_team_agg['avg_starting_position']
x = kickoffs_team_agg['scoring_rate_on_drives_following_kickoffs']
image_urls = kickoffs_team_agg['url']

# Create a basic scatter plot
fig = go.Figure()

# Add scatter points with invisible markers (we'll replace them with images)
fig.add_trace(go.Scatter(
    x=x, # Map 'x' data set to x axis
    y=y, # Map 'y' data set to y axis
    mode='markers',
    marker=dict(opacity=0)  # Make markers invisible
))

# Calculate the range of your x and y data
x_range = max(x) - min(x)
y_range = max(y) - min(y)

# Define the size factor based on the data range to dynamically size logos
size_factor_x = x_range * .1
size_factor_y = y_range * .1

# Add images to the scatter plot by looping through all the records from the team data set
for i, url in enumerate(image_urls): # for each record in our image_urls data set defined above, add an image with the below properties
    fig.add_layout_image(
        dict(
            source=url, # Identifies the source field to use as images from the image_urls data set
            xref="x", # Determines which axis the x position of the image is relative to. When set to "x", the x coordinate of the image is relative to the x-axis of the plot.
            yref="y", # Determines which axis the y position of the image is relative to. When set to "y", the y coordinate of the image is relative to the y-axis of the plot.
            x=x[i],  # x position of the image
            y=y[i],  # y position of the image
            sizex=size_factor_x,  # Dynamically size to ensure stability as the scale changes
            sizey=size_factor_y, # Dynamically size to ensure stability as the scale changes
            xanchor="center", # Adjust the alignment of the image as needed for the x-axis
            yanchor="middle" # Adjust the alignment of the image as needed for the y-axis
        )
    )

# Customize layout
fig.update_layout(
    title="Scoring Rate by Average Starting Field Position", # Assign visual title
    xaxis_title="Scoring Rate on Drives Following Kickoffs", # Assign x-axis title
    yaxis_title="Average Starting Field Position", # Assign y-axis title
    height=600,  # Set the height of the chart
    xaxis=dict( # Apply data formatting to the x-axis (rounded to 1 decimal)
        showgrid=True,
        tickformat='.1%'  # Format x-axis labels to one decimal place
    ),
    yaxis=dict( # Apply data formatting to the y-axis (rounded to 1 decimal)
        showgrid=True,
        tickformat='.1f'
    )
)

# Display scatter plot in streamlit app
st.plotly_chart(fig)

# ----------------------- Combo graph ----------------------
st.header(f"Kickoff Analysis", divider='gray')

# Sort by season to avoid out-of-order connections
kickoffs_agg = kickoffs_agg.sort_values('season')

# Define values for the bars and line graph
season = kickoffs_agg['season']
return_rate = kickoffs_agg['return_rate']
scoring_rate = kickoffs_agg['scoring_rate_on_drives_following_kickoffs']
avg_starting_field_position = kickoffs_agg['avg_starting_position_returns']

# Create a Plotly figure
fig = go.Figure()

# Add grouped bars for Return Rate and Scoring Rate
fig.add_trace(go.Bar(x=season, y=return_rate, name='Return Rate', yaxis='y1', marker_color='#660066'))
fig.add_trace(go.Bar(x=season, y=scoring_rate, name='Scoring Rate', yaxis='y1', marker_color='#CC99CC'))

# Add line for Average Starting Field Position (on secondary y-axis)
fig.add_trace(go.Scatter(x=season, y=avg_starting_field_position, mode='lines+markers', name='Avg. Starting Field Position', yaxis='y2', marker_color='#999999'))

# Add a target line for Return Rate at 50% (dotted line)
fig.add_trace(go.Scatter(
    x=season, # Assign the season data set to the x axis
    y=[0.55] * len(season),  # Constant 55% target line
    mode='lines', 
    name='Target Return Rate (55%)', # Target line graph label
    line=dict(dash='dot', color='black'),  # Set line to be dotted and red
    yaxis='y1'  # Attach this line to the primary y-axis (Return Rate)
))

# Update layout for better formatting, including secondary y-axis
fig.update_layout(
    title="Return Rate, Scoring Rate, and Avgerage Starting Field Position by Season",
    xaxis_title='Season',
    yaxis=dict(
        title='Return/Scoring Rate (%)',
        tickformat=',.1%',  # Format y1-axis as percentage
        side='left', # Identifies which side to plot the ticks and labels
        range=[.2,.6] # Hardcoded range of values. This can be set to auto, but I liked the fixed axis
    ),
    yaxis2=dict(
        title='Avg. Starting Field Position (Yard Line)',
        overlaying='y',  # Overlay y2 on the same plot
        side='right',  # Position y2 on the right side
        showgrid=False,  # Disable grid lines for y2 to avoid clutter
        range=[20,40]
    ),
    barmode='group',  # Group the bars side by side
    legend=dict(
        orientation="h",  # Horizontal layout for the legend
        yanchor="top",  # Align the top of the legend
        y=-0.2,  # Push the legend below the chart
        xanchor="center",  # Center the legend
        x=0.5  # Center the legend horizontally
    ),
    plot_bgcolor='white', # Sets the background color of the visual to white
    hovermode='x unified',  # Show hover info across all bars/lines at the same x value
)

# Show the chart in Streamlit
st.plotly_chart(fig)

# Add reference to 55% return rate target
st.markdown("[Kickoff Rules Explained](https://www.espn.com/nfl/story/_/id/40647523/nfl-kickoff-rules-changes-do-coaches-players-expect)", unsafe_allow_html=True)

# Breakout of touchdowns vs. field goals

# ----------------------- TD vs. FG graph ----------------------
st.header(f"Scoring Analysis", divider='gray')

# Sort by season to avoid out-of-order x axis
kickoffs_agg = kickoffs_agg.sort_values('season')

# Define values for the bars and line graph
season = kickoffs_agg['season']
td_rate = kickoffs_agg['td_rate_on_drives_following_kickoffs']
fg_rate = kickoffs_agg['fg_rate_on_drives_following_kickoffs']

# Create a Plotly figure
fig = go.Figure()

# Add grouped bars for Return Rate and Scoring Rate
fig.add_trace(go.Scatter(x=season, y=td_rate, name='Touchdown Rate Following Kickoffs', yaxis='y1', marker_color='#660066'))
fig.add_trace(go.Scatter(x=season, y=fg_rate, name='Field Goal Rate Following Kickoffs', yaxis='y1', marker_color='#CC99CC'))

# Update layout for better formatting, including secondary y-axis
fig.update_layout(
    title="Touchdown and Field Goal Scoring Rates on Drives Following Kickoffs", # Graph title
    xaxis_title='Season', # x axis title
    yaxis=dict(
        title='Return/Scoring Rate (%)', # y axis title
        tickformat=',.1%',  # Format y1-axis as percentage
        side='left'
    ),
    legend=dict(
        orientation="h",  # Horizontal layout for the legend
        yanchor="top",  # Align the top of the legend
        y=-0.2,  # Push the legend below the chart
        xanchor="center",  # Center the legend
        x=0.5  # Center the legend horizontally
    ),
    plot_bgcolor='white',
    hovermode='x unified',  # Show hover info across all bars/lines at the same x value
)

# Show the chart in Streamlit
st.plotly_chart(fig)

# -------- Penalty Analysis ---------------------

st.header(f"Kickoff Penalty Analysis", divider='gray')

# Aggregate the penalty rate by penalty_type across all seasons
penalty_order = penalty_agg.groupby('penalty_type')['penalty_rate'].sum().sort_values(ascending=False).index

# Convert 'penalty_type' to a categorical type based on the penalty order
penalty_agg['penalty_type'] = pd.Categorical(penalty_agg['penalty_type'], categories=penalty_order, ordered=True)

# Ensure the seasons are sorted in chronological order (assuming 'season' is numerical or categorical)
penalty_agg = penalty_agg.sort_values(by=['season', 'penalty_type'], ascending=[True, True])

# Create the horizontal bar chart
fig = px.bar(
    penalty_agg,
    x='penalty_rate', # The x-axis will reflect the penalty rate
    y='penalty_type',  # The y-axis will now reflect the sorted penalty types
    facet_col='season',  # Keep season sorting as per original
    orientation='h', # set bars to horizontal bars instead of traditional vertical ones
    title='Penalty Distribution by Year', # Graph title
    labels={'penalty_rate': 'Penalty Rate', 'penalty_type': 'Penalty Type'} # Assign axis labels to data sets
)

# Update layout for better formatting and outer borders
fig.update_layout(
    height=800, # fixed height
    showlegend=False, # Hide legend
    plot_bgcolor='white', # Set background to white
    title_x=0.5, # centers title along axis
    title_pad=dict(t=60), # creates some white space between the header and graph
    margin=dict(l=40, r=40, t=80, b=40), # additional padding options around margins
)

# Customize x-axis to show separators between groups dynamically
fig.for_each_xaxis(lambda xaxis: xaxis.update(
    showgrid=False, # hide grids
    showline=True, # display verticle grid line separating years along x axis
    linewidth=.5, # makes verticle grid line thin
    linecolor='#e0e0e0', # makes verticle grid line very light grey
    ticks="",  # Completely remove tick marks
    # Hide tick marks and data labels along x axis
    showticksuffix=None,
    tickmode=None,
    showticklabels=False,
    title=None,
    tickformat='.1%' # format data values if the x axis were to display data labels
))

# Customize y-axis to show only outer borders
fig.for_each_yaxis(lambda yaxis: yaxis.update(
    showgrid=False,
    showline=True,
    linewidth=.5, 
    linecolor='#e0e0e0'
))

# Update bar color to #660066
fig.update_traces(
    marker_color='#660066',
    hovertemplate='%{y}: %{x:.1%}<extra></extra>'  # Format hovertemplate to show percentage with one decimal
)

# Display the Plotly chart in Streamlit
st.plotly_chart(fig)

st.markdown("[MIT License: Data retrieved from nfl_data_py Python package](https://github.com/datacoaching/NFLAnalytics/blob/main/LICENSE.txt)", unsafe_allow_html=True)

