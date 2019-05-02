#!/usr/bin/env python3

import argparse
import curses
import re
import requests
import time

from datetime import datetime


# API request header to get access to NBA data as though we
#  were using a browser
HEADERS = {
    'user-agent': ('Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/57.0.2987.133 Safari/537.36'),  # noqa: E501
    'Dnt': ('1'),
    'Accept-Encoding': ('gzip, deflate, sdch'),
    'Accept-Language': ('en'),
    'origin': ('http://stats.nba.com'),
}


def resultsets2dict(results):
    '''
    NBA data api returns data in an unintuitive list with a
    headers key to decode each element. This converts that 
    format into a more usable python dictionary

    Args:
        results (dict): results from NBA data api request

    Returns:
        dict: dictionary of api results in easier format
            to code with
    '''
    d = {}
    for resultset in results['resultSets']:
        d[resultset['name']] = []
        rowset = []
        lookup = {i: v for i, v in enumerate(resultset['headers'] )}
        for r in resultset['rowSet']:
            row = {lookup[i]:v for i, v in enumerate(r)}
            d[resultset['name']].append(row)
    return d


class NBAGame(object):
    '''
    Class to hold NBA game data read off of data.nba.com api
    '''
    def __init__(self, summary_dict, game_id):
        self.game_id = game_id

        # Get GameHeader for game, and parse it's data
        for game_header in summary_dict['GameHeader']:
            if game_header['GAME_ID'] == game_id:
                self.game_header = game_header
        self.home_team_id = self.game_header['HOME_TEAM_ID']
        self.away_team_id = self.game_header['VISITOR_TEAM_ID']
        self.game_status = self.game_header['GAME_STATUS_TEXT']
        self.live_period = self.game_header['LIVE_PERIOD']
        self.live_pc_time = self.game_header['LIVE_PC_TIME']

        # Parse the linescore data for the home and away teams
        for ls in summary_dict['LineScore']:
            if ls['TEAM_ID'] == self.away_team_id:
                self.away_abbr = ls['TEAM_ABBREVIATION']
                self.away_city = ls['TEAM_CITY_NAME']
                self.away_win_loss = ls['TEAM_WINS_LOSSES']
                self.away_pts = ls['PTS'] if ls['PTS'] else '0'
                self.away_quarter2pts = {k:v for k,v in ls.items() if 'PTS_' in k}
                self.away_fg_pct = ls['FG_PCT']
                self.away_ft_pct = ls['FT_PCT']
                self.away_fg3_pct = ls['FG3_PCT']
                self.away_ast = ls['AST']
                self.away_reb = ls['REB']
                self.away_tov = ls['TOV']

            if ls['TEAM_ID'] == self.home_team_id:
                self.home_abbr = ls['TEAM_ABBREVIATION']
                self.home_city = ls['TEAM_CITY_NAME']
                self.home_win_loss = ls['TEAM_WINS_LOSSES']
                self.home_pts = ls['PTS'] if ls['PTS'] else '0'
                self.home_quarter2pts = {k:v for k,v in ls.items() if 'PTS_' in k}
                self.home_fg_pct = ls['FG_PCT']
                self.home_ft_pct = ls['FT_PCT']
                self.home_fg3_pct = ls['FG3_PCT']
                self.home_ast = ls['AST']
                self.home_reb = ls['REB']
                self.home_tov = ls['TOV']

        # Make some accessible displays of data
        self.title = f'{self.away_city} v {self.home_city}'
        self.score = f'{self.away_pts} - {self.home_pts}'
        self.topline = f'{self.away_abbr} {self.score} {self.home_abbr}\t{self.live_pc_time}{self.game_status}'

    def box_score(self, tab_size=5):
        '''
        Make a box score for the game

        Args:
            tab_size (int): width in characters for box cells (default=5)
        '''
        def _align_text(text):
            text = str(text)
            right_spaces = 1
            left_spaces = tab_size - right_spaces - len(text)
            return ' '*left_spaces + text + ' '*right_spaces

        columns = [k for k, v in self.away_quarter2pts.items() if (v or 'OT' not in k)]
        columns_clean = [c.replace('PTS_QTR', 'Q').replace('PTS_OT', 'OT') for c in columns]

        header = '|'.join(map(_align_text, [''] + columns_clean))
        fill = '+'.join(['-'*tab_size for _ in range(len(columns)+1)])
        away = '|'.join(map(_align_text, [self.away_abbr] + [(self.away_quarter2pts[c] or '-') for c in columns]))
        home = '|'.join(map(_align_text, [self.home_abbr] + [(self.home_quarter2pts[c] or '-') for c in columns]))
        return '\n'.join([header, fill, away, home]) 


class NBAScoresCLI(object):
    '''
    Defines curses CLI app for interacting with NBA game data
    '''
    def __init__(self, stdscr, date, games, refresh_delay=30):
        k = 0
        self.refresh_delay = refresh_delay
        self.stdscr = stdscr
        self.focus = -1
        self.extra_status_text = '# to select game'
        self.height = None
        self.width = None

        # Clear and refresh the screen for a blank canvas
        self.stdscr.clear()
        self.stdscr.refresh()

        # # Start colors in curses
        curses.start_color()
        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(4, 247, curses.COLOR_BLACK)

        # Loop where k is the last character pressed
        while (k != ord('q')):

            # Initialization
            self.stdscr.clear()
            self.height, self.width = self.stdscr.getmaxyx()

            # Update data
            if int(time.time()) % 5 == 0:
                d = get_nba_scoreboard(date, offset=offset)
                games = [NBAGame(d, game['GAME_ID']) for game in d['GameHeader']]

            # Check for keyboard inputs
            if k in [ord(str(x)) for x in range(len(games))]:
                self.focus = int(chr(k))
                self.extra_status_text = "Press 'b' to back"
            elif k == ord('b'):
                self.focus = -1
                self.extra_status_text = 'Press (#) to select game'

            # If there is a game in focus display that game, else all games
            if self.focus > -1:
                self._display_game()
            else:
                self._display_all_games()
            
            # Display the status bar
            self._display_status_bar()

            # Update data
            if int(time.time()) % self.refresh_delay == 0:
                self.extra_status_text = "adfadfadsf"
                stdscr.nodelay(1)
                self.stdscr.refresh()
                stdscr.nodelay(0)
                
            # Display and get keystroke
            self.stdscr.refresh()
            k = self.stdscr.getch()


    def _display_game(self):
        '''
        Display game details for the game of focus
        '''
        game = games[self.focus]
        self._write_centered_text(2, game.title)
        self._write_centered_text(3, game.score)
        self._write_centered_text(4, game.game_status)

        for i, line in enumerate(game.box_score().split('\n')):
            self._write_centered_text(4+i, line)

        self._write_center_column(12, game.away_abbr)
        self._write_center_column(13, f' FG% : {game.away_fg_pct}')
        self._write_center_column(14, f' FT% : {game.away_ft_pct}')
        self._write_center_column(15, f'3pt% : {game.away_fg3_pct}')
        self._write_center_column(16, f' Ast : {game.away_ast}')
        self._write_center_column(17, f' Reb : {game.away_reb}')
        self._write_center_column(18, f'  TO : {game.away_tov}')

        self._write_center_column(12, game.home_abbr, column='right')
        self._write_center_column(13, f' FG% : {game.home_fg_pct}', column='right')
        self._write_center_column(14, f' FT% : {game.home_ft_pct}', column='right')
        self._write_center_column(15, f'3pt% : {game.home_fg3_pct}', column='right')
        self._write_center_column(16, f' Ast : {game.home_ast}', column='right')
        self._write_center_column(17, f' Reb : {game.home_reb}', column='right')
        self._write_center_column(18, f'  TO : {game.home_tov}', column='right')


    def _display_all_games(self):
        '''
        Display list of games, their scores, and status
        '''
        start_x = 2
        self._write_centered_text(start_x, 'GAMES', curses.color_pair(2))         
        for i, game in enumerate(games):
            game_str = f'({i}) {game.topline}'
            self._write_centered_text(start_x+1+i, game_str, curses.color_pair(1))

    def _display_status_bar(self):
        '''
        Make Display status bar at bottom of screen
        '''
        statusbarstr = f"Press 'q' to exit | {self.extra_status_text}"
        self.stdscr.attron(curses.color_pair(3))
        self.stdscr.addstr(self.height-1, 0, statusbarstr)
        self.stdscr.addstr(self.height-1, len(statusbarstr), " " * (self.width - len(statusbarstr) - 1))
        self.stdscr.attroff(curses.color_pair(3))

    def _write_centered_text(self, y, text, color=None):
        '''
        Write text at centered in screen

        Args:
            y (int): y coord for text
            text (str): string to center
        '''
        x_start = int((self.width // 2) - (len(text) // 2) - len(text) % 2)
        if color:
            self.stdscr.addstr(y, x_start, text, color)
        else:
            self.stdscr.addstr(y, x_start, text)

    def _write_center_column(self, y, text, column='left', color=None):
        '''
        Write text at center of a given column {'left'|'right'}

        Args:
            y (int): y coord for text
            text (str): string to center
            column (str): left or right column (default='left')
        '''
        x_start = int((self.width // 4) - (len(text) // 2) - len(text) % 2)
        if column == 'right':
            x_start += int((self.width // 2))
        if color:
            self.stdscr.addstr(y, x_start, text, color)
        else:
            self.stdscr.addstr(y, x_start, text)


def get_nba_scoreboard(date, offset=0):
    response = requests.get(f'https://stats.nba.com/stats/scoreboardv2?gamedate={date}&leagueid=00&dayoffset={offset}', headers=HEADERS)
    return resultsets2dict(response.json())


if __name__ == '__main__':
    # CLI arguments
    parser = argparse.ArgumentParser(description='CLI app to check NBA scores')
    parser.add_argument('--offset', dest="offset", default=0, type=int, help='Days offset from today')
    parser.add_argument('--date', dest="date", default=datetime.strftime(datetime.today().date(), '%m-%d-%Y'),
                        type=str, help='Reference Date eg "01-15-2019" (default: today)')
    args = parser.parse_args()
    offset = args.offset
    date = args.date

    # Validate and process date
    if not re.match(r'^[01]\d-[0123]\d-\d{4}$', date):
        raise ValueError("Invalid date input; use dashes and zero-pad like 01-15-2018")
    date = date.replace('-', '/')

    # Do the API stuff
    d = get_nba_scoreboard(date=date, offset=offset)
    games = [NBAGame(d, game['GAME_ID']) for game in d['GameHeader']]
    
    # Launch the CLI
    if not games:
        print("No games found for given day")
    else:
        curses.wrapper(NBAScoresCLI, date, games)
