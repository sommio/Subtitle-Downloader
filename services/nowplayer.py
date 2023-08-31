#!/usr/bin/python3
# coding: utf-8

"""
This module is to download video from NowPlayer
"""
from pathlib import Path
import sys
import os
import shutil
import time
from urllib.parse import parse_qs, urlparse
from requests.utils import cookiejar_from_dict
from configs.config import config, credentials, user_agent
from utils.io import rename_filename
from utils.subtitle import convert_subtitle
from services.service import Service


class NowPlayer(Service):
    """
    Service code for Now Player streaming service (https://www.nowtv.now.com/).

    Authorization: Cookies
    """

    def __init__(self, args):
        super().__init__(args)

    def generate_caller_reference_no(self):
        return f"NPXWC{int(time.time() * 1000)}"

    def movie_metadata(self, content_id):
        self.cookies['LANG'] = 'en'
        self.session.cookies.update(cookiejar_from_dict(
            self.cookies, cookiejar=None, overwrite=True))

        res = self.session.get(
            self.config['api']['movie'].format(product_id=content_id))

        if res.ok:
            data = res.json()[0]

            title = data['episodeTitle']
            release_year = ""

            chinese_cookies = self.cookies
            chinese_cookies['LANG'] = 'zh'
            self.session.cookies.update(cookiejar_from_dict(
                chinese_cookies, cookiejar=None, overwrite=True))
            chinese_title = self.session.get(
                self.config['api']['movie'].format(product_id=content_id)).json()[0]['episodeTitle']

            movie_info = self.get_movie_info(
                title=chinese_title, title_aliases=[title])
            if movie_info:
                release_year = movie_info['release_date'][:4]

            self.logger.info("\n%s (%s) [%s]", title,
                             chinese_title, release_year)

            default_language = data['language']

            file_name = f'{title} {release_year}'

            folder_path = os.path.join(
                self.download_path, rename_filename(file_name))

            self.download_subtitle(content_id=data['episodeId'],
                                   title=file_name, folder_path=folder_path, default_language=default_language)

            convert_subtitle(folder_path=folder_path,
                             platform=self.platform, lang=self.locale)

            if self.output:
                shutil.move(folder_path, self.output)

        else:
            self.logger.error(res.text)
            sys.exit(1)

    def series_metadata(self, content_id):
        self.cookies['LANG'] = 'en'
        self.session.cookies.update(cookiejar_from_dict(
            self.cookies, cookiejar=None, overwrite=True))

        res = self.session.get(
            self.config['api']["series"].format(series_id=content_id))

        if res.ok:
            data = res.json()[0]
            title = data['brandName']
            season_index = int(data['episode'][0]['seasonNum'])
            if season_index == 0:
                season_index = 1

            season_name = str(season_index).zfill(2)

            self.logger.info("\n%s Season %s", title, season_index)

            folder_path = os.path.join(
                self.download_path, f'{rename_filename(title)}.S{season_name}')

            episode_list = data['episode']

            episode_num = len(episode_list)

            if self.last_episode:
                episode_list = [episode_list[-1]]
                self.logger.info("\nSeason %s total: %s episode(s)\tdownload season %s last episode\n---------------------------------------------------------------",
                                 season_index,
                                 episode_num,
                                 season_index)
            else:
                self.logger.info("\nSeason %s total: %s episode(s)\tdownload all episodes\n---------------------------------------------------------------",
                                 season_index,
                                 episode_num)

            for episode in episode_list:
                episode_index = int(episode['episodeNum'])
                if not self.download_season or season_index in self.download_season:
                    if not self.download_episode or episode_index in self.download_episode:
                        content_id = episode['episodeId']
                        file_name = f'{title} S{season_name}E{str(episode_index).zfill(2)}'

                        self.logger.info("\n%s", file_name)

                        self.download_subtitle(content_id=content_id,
                                               title=file_name, folder_path=folder_path)

            convert_subtitle(folder_path=folder_path,
                             platform=self.platform, lang=self.locale)

            if self.output:
                shutil.move(folder_path, self.output)

        else:
            self.logger.error(res.text)
            sys.exit(1)

    def download_subtitle(self, content_id, title, folder_path, default_language=""):
        data = {
            'callerReferenceNo': self.generate_caller_reference_no(),
            'productId': content_id,
            'isTrailer': 'false',
        }

        res = self.session.post(
            self.config['api']["play"], data=data)
        if res.ok:
            data = res.json()
            if not data.get('asset'):
                if data.get('responseCode') == "NEED_LOGIN":
                    self.logger.error(
                        "Please renew the cookies, and make sure config.py USERR_AGENT is same as login browser!")
                    os.remove(
                        Path(config.directories['cookies']) / credentials[self.platform]['cookies'])
                    sys.exit(1)
                else:
                    self.logger.error("Error: %s", data.get('responseCode'))
                    sys.exit(1)
        else:
            self.logger.error("Failed to get tracks: %s", res.text)
            sys.exit(1)

        media_src = next(
            (url for url in data["asset"] if '.mpd' in url), data["asset"][0])

        if '.mpd' in media_src:
            mpd_url = media_src

            headers = {
                'user-agent': user_agent,
                'referer': 'https://nowplayer.now.com/'
            }

            timescale = self.ripprocess.get_time_scale(mpd_url, headers)

            self.ripprocess.download_subtitles_from_mpd(
                url=mpd_url, title=title, folder_path=folder_path, headers=headers, proxy=self.proxy, debug=False, timescale=timescale)

        else:
            print()

    def main(self):
        params = parse_qs(urlparse(self.url).query)

        if params.get('id'):
            content_id = params.get('id')[0]
        else:
            self.logger.error("\nUnable to find content id!")
            sys.exit(1)

        if params.get('type') and params.get('type')[0] == 'product':
            self.movie_metadata(content_id)
        else:
            self.series_metadata(content_id)
