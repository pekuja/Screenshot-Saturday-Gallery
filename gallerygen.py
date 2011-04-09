import tweepy
import re
import sqlite3
import urllib
import django
import os
import Image
import codecs
from datetime import datetime, timedelta
from django.template import Context, Template
from BeautifulSoup import BeautifulSoup

tweets_per_page = 100
tag = '#screenshotsaturday'
url_regex = re.compile(r'\b(http://[^\ ]+)\b')
retweet_regex = re.compile(r'\bRT\b')
sqlite_db = 'screenshots.sqlite3'
url_shorteners = ('bit.ly', 'j.mp', 'ow.ly', 'tinyurl.com', 'goo.gl', 't.co', 'ping.fm', 'drbl.in')

def create_db(conn, cursor):
    try:
        cursor.execute('''create table screenshots
        (tweet_id integer, user text, ts timestamp,
        original_url text, tweet_text text, url text, ignore boolean)''')
        conn.commit()
    except:
        print 'table already created, move on...'

def get_tweets(conn, cursor):
    previous_last_id = ''
    last_id = ''
    page_num = 1
    while page_num < 1600/tweets_per_page:
        print "reading page %s" % page_num 
        tweets = tweepy.api.search(tag, rpp=tweets_per_page, page=page_num)
        quit_out = False
        if last_id == '':
            last_id = tweets[0].id_str
        print "read %s tweets" % len(tweets)
        for tweet in tweets:
            # Check if we've been here
            print "User: @%s" % tweet.from_user.encode('ascii', 'ignore')
            print "Tweet: %s" % tweet.text.encode('ascii', 'ignore')
            cursor.execute('select tweet_id from screenshots where tweet_id = ?', (tweet.id,))
            row = cursor.fetchone()
            if row:
                print "already read these. bailing out"
                #quit_out = True
                continue
            
            # Ignore retweets
            if re.search(retweet_regex, tweet.text):
                print "Retweet. Ignoring."
                continue
            
            # Extract URL
            #url = re.search(url_regex, tweet.text)
            for num,url in enumerate(re.findall(url_regex, tweet.text)):
                print "extracting url " + str(num + 1) + ": " + url
                #url = url.group(1)
                cursor.execute('''insert into screenshots
                               values (?, ?, ?, ?, ?, NULL, NULL)''',
                               (tweet.id, tweet.from_user,
                               tweet.created_at, url, tweet.text))
                conn.commit()
                                    
        page_num += 1
        
        if len(tweets) < tweets_per_page:
            break
        
        if quit_out:
            break
    
    cursor.execute('''delete from screenshots where ts not in
    (select min(ts) from screenshots group by original_url)''')
    conn.commit()
    
def download_image(url, filename):
    uo = urllib.urlopen(url)
    mime = uo.info()
    if mime.getmaintype() == 'image':
        img_type = mime.getsubtype()
        if img_type == 'jpeg':
            img_type = 'jpg'
        if not filename.lower().endswith('.%s' % img_type):
            filename += '.%s' % img_type
        img_file = open('images/%s' % filename, 'w+b')
        img_file.write(uo.read())
        img_file.close()
        return filename
    else:
        raise 'not an image'

def download_images(conn, cursor):
    cursor.execute('select tweet_id, ts, user, original_url, url, tweet_text from screenshots where url is null')# and ignore is null')
    
    for (tweet_id, timestamp, user, orig_url, url, tweet_text) in cursor.fetchall():
        old_url = orig_url
        if not url:
            # Get rid of URL shortener redirects
            if orig_url.split('/')[2] in url_shorteners:
                try:
                    uo = urllib.urlopen(orig_url)
                    orig_url = uo.geturl()
                    print "url shortener: %s -> %s" % (old_url, orig_url)
                    cursor.execute('update screenshots set original_url=? where original_url=?', (orig_url, old_url))
                    conn.commit()
                    old_url = orig_url
                    uo.close()
                except:
                    print 'failed to open %s' % orig_url
            if orig_url.startswith('http://twitpic.com/'):
                try:
                    print 'twitpic image: %s' % orig_url
                    if orig_url.find('full') == -1:
                        if not orig_url.endswith('/'):
                            orig_url += '/'
                        orig_url += 'full'
                    print 'orig_url: %s' % orig_url
                    name = re.search('http://twitpic.com/(\w+)/full', orig_url).group(1)
                    
                    uo = urllib.urlopen(orig_url)
                    bs = BeautifulSoup(uo.read())
                    imgs = bs.findAll('img')
                    img_url = imgs[1]['src']
                    uo.close()
                    url = download_image(img_url, 'twitpic_%s' % name)
                except:
                    print 'reading twitpic image failed'
            elif orig_url.startswith('http://yfrog.com/'):
                try:
                    print 'yfrog image "%s"' % orig_url
                    filename = re.search('http://yfrog.com/(f/)?(\w+)', orig_url).group(2)
                    
                    api_url = 'http://yfrog.com/api/xmlInfo?path=%s' % filename
                    filename = 'yfrog_' + filename
                    print 'yfrog api url "%s"' % api_url
                    uo = urllib.urlopen(api_url)
                    bs = BeautifulSoup(uo.read())
                    #bs = BeautifulSoup(uo.read())
                    #og_image = bs.find('meta', {'property': 'og:image'})
                    #img_url = og_image['content']
                    img_url = bs.find('image_link').contents[0]
                    uo.close()
                    url = download_image(img_url, filename)
                except:
                    print 'reading yfrog image failed'
            elif orig_url.startswith('http://plixi.com/'):
                try:
                    print 'plixi image %s' % orig_url
                    filename = 'plixi_%s' % orig_url.split('/')[-1]
                    
                    uo = urllib.urlopen(r'http://api.plixi.com/api/tpapi.svc/imagefromurl?size=big&url=' + orig_url)
                    if uo.info().getmaintype() == 'image':
                        filename += '.' + uo.info().getsubtype()
                        img_file = open('images/' + filename, 'w+b')
                        img_file.write(uo.read())
                        img_file.close()
                        url = filename
                    else:
                        print 'plixi image is of mimetype %s' % uo.info().gettype()
                        print 'trying to guess image format'
                        header = uo.read(10)
                        if header[1:4] == 'PNG':
                            print 'PNG'
                            filename += '.png'
                        elif header[0:3] == 'GIF':
                            print 'GIF'
                            filename += '.gif'
                        elif header[6:10] == 'JFIF':
                            print 'JPEG'
                            filename += '.jpg'
                        else:
                            print 'unable to determine image format'
                            print 'header contents: ' + header
                            raise'getout'
                        img_file = open('images/' + filename, 'w+b')
                        img_file.write(header)
                        img_file.write(uo.read())
                        img_file.close()
                        url = filename
                except IOError, error:
                    print error
                    print 'reading plixi image failed'
                except:
                    print 'reading plixi image failed'
            elif orig_url.startswith('http://www.flickr.com/'):
                try:
                    print 'flickr image %s' % orig_url
                    filename = 'flickr_%s_%s' % (orig_url.split('/')[-3], orig_url.split('/')[-2])
                    
                    uo = urllib.urlopen(orig_url)
                    bs = BeautifulSoup(uo.read())
                    photo = bs.find('img', alt='photo')
                    img_url = photo['src']
                    uo.close()
                    url = download_image(img_url, filename)
                except:
                    print 'reading flickr image failed'
            elif orig_url.startswith('http://d.pr/'):
                try:
                    print 'droplr image %s' % orig_url
                    filename = 'droplr_%s' % orig_url.split('/')[-1]
                    
                    uo = urllib.urlopen(orig_url)
                    bs = BeautifulSoup(uo.read())
                    img_url = bs.find('div', id='image').img['src']
                    uo.close()
                    url = download_image(img_url, filename)
                except:
                    print 'reading droplr image failed'
            elif orig_url.startswith('http://ow.ly/'):
                try:
                    print 'ow.ly image %s' % orig_url
                    
                    if not orig_url.endswith('original'):
                        orig_url += '/original'
                        
                    name = orig_url.split('/')[-2]
                    
                    uo = urllib.urlopen(orig_url)
                    bs = BeautifulSoup(uo.read())
                    img_url = bs.find('div', {'class': 'imageWrapper'}).img['src']
                    filename = 'owly_' + img_url.split('/')[-1]
                    uo.close()
                    url = download_image(img_url, filename)
                except:
                    print 'reading ow.ly image failed'
            elif orig_url.startswith('http://brizzly.com/'):
                try:
                    print 'brizzly image %s' % orig_url
                    
                    uo = urllib.urlopen(orig_url)
                    bs = BeautifulSoup(uo.read())
                    img_url = bs.find('div', id='original_image_link').a['href']
                    filename = 'brizzly_%s' % img_url.split('/')[-1]
                    uo.close()
                    url = download_image(img_url, filename)
                except:
                    print 'reading brizzly image failed'
            elif orig_url.startswith('http://imgur.com/'):
                try:
                    print 'imgurl image %s' % orig_url
                    
                    uo = urllib.urlopen(orig_url)
                    bs = BeautifulSoup(uo.read())
                    img_url = bs.find('link', rel='image_src')['href']
                    filename = 'imgur_%s' % img_url.split('/')[-1]
                    uo.close()
                    url = download_image(img_url, filename)
                except:
                    print 'reading imgur image failed'
            elif orig_url.startswith('https://www.dropbox.com/'):
                orig_url = orig_url.replace('www.dropbox.com', 'dl.dropbox.com')
            elif orig_url.startswith('http://dribbble.com/shots/'):
                try:
                    print 'dribbble image %s' % orig_url
                    
                    uo = urllib.urlopen(orig_url)
                    bs = BeautifulSoup(uo.read())
                    img_url = 'http://dribbble.com' + bs.find('div', id='single-img').img['src']
                    filename = 'dribbble_%s' % orig_url.split('/')[-1]
                    uo.close()
                    url = download_image(img_url, filename)
                except:
                    print 'reading dribble image failed'
            
            if not url:
                    try:
                        uo = urllib.urlopen(orig_url)
                        mime = uo.info()
                        if mime.getmaintype() == 'image':# or \
                            #orig_url.endswith('.png') or orig_url.endswith('.jpg'):
                            uo.close()
                            print 'straight up image link %s' % orig_url
                            img_url = orig_url
                            filename = 'directlink_' + re.search(r'/([^/]+)$', img_url).group(1)
                            url = download_image(img_url, filename)
                        else:
                            print "couldn't load %s" % orig_url
                            print 'mimetype: %s' % mime.gettype()
                    except:
                        print 'loading %s failed' % orig_url

            if url:
                print 'updating url %s to %s' % (old_url, url)
                cursor.execute('update screenshots set url=? where original_url=?', (url, old_url))
                conn.commit()
            else:
                print 'ignoring url %s' % (old_url, )
                cursor.execute('update screenshots set ignore=1 where original_url=?', (old_url,))
                conn.commit()

def generate_thumbnails():
    for filename in os.listdir('images'):
        if not os.path.exists('square/%s' % filename):
            try:
                print "cropping image %s" % filename
                img = Image.open('images/%s' % filename)
                dim = min(img.size)
                cropped = img.transform((dim, dim), Image.EXTENT, (img.size[0]/2-dim/2, img.size[1]/2-dim/2, img.size[0]/2+dim/2, img.size[1]/2+dim/2))
                cropped.thumbnail((200,200), Image.ANTIALIAS)
                cropped.save('square/%s' % filename)
            except IOError, error:
                print error
                print "couldn't make a square thumbnail out of %s" % filename

def delete_duplicates(conn, cursor):
    cursor.execute('''delete from screenshots where ts not in
    (select min(ts) from screenshots group by url)''')
    conn.commit()
    
def generate_gallery_html(conn, cursor):
    print 'Writing HTML'
    
    cursor.execute('select date(min(ts),"-7 days", "weekday 5", "start of day") from screenshots where url is not null and ignore is null')
    start_date = cursor.fetchone()[0]
    cursor.execute('select max(ts) from screenshots where url is not null')
    end_date = cursor.fetchone()[0]
    
    curr_date = start_date
    
    django.conf.settings.configure()
    template = Template(codecs.open('templates/gallery_template.html', 'r+', encoding='utf-8').read())
    json_template = Template(codecs.open('templates/images_template.js', 'r+', encoding='utf-8').read())
    page_num = 1

    last_page = False
    week_num = 1
    while not last_page:
        cursor.execute('select distinct user, tweet_text, url, ts from screenshots where url is not null and ts between date(?, "+%s days") and date(?, "+%s days") order by ts desc' % (7*(week_num-1), 7*week_num), (curr_date, curr_date))
        
        query_results = cursor.fetchall()
        
        if len(query_results) != 0:
            print "Writing page #%s" % page_num
            context = None
            context_dict = {'screenshots': query_results}
            if page_num > 1:
                context_dict['prev_page'] = 'week%s.html' % (page_num - 1)
            cursor.execute('select (date(?, "+%s days") > date(?))' % (7 * week_num,), (curr_date, end_date))
            last_page = cursor.fetchone()[0]
            cursor.execute('select date(?, "+%s days")' % (7 * week_num - 6), (curr_date,))
            saturday = cursor.fetchone()[0]
            context_dict['saturday'] = saturday
            context_dict['week_num'] = week_num
            if not last_page:
                cursor.execute('select (date(?, "+%s days") > date(?))' % (7 * (week_num+1),), (curr_date, end_date))
                next_to_last_page = cursor.fetchone()[0]
                if not next_to_last_page:
                    context_dict['next_page'] = 'week%s.html' % (page_num + 1)
                else:
                    context_dict['next_page'] = 'index.html'
                
            context = Context(context_dict)
            
            page_render = template.render(context)
            
            if last_page:
                f = codecs.open('index.html', 'w+', encoding='utf-8')
                f.write(page_render)
                f = codecs.open('images.js', 'w+', encoding='utf-8')
                json_render = json_template.render(context)
                f.write(json_render)
            else:
                f = codecs.open('week%s.html' % page_num, 'w+', encoding='utf-8')
                f.write(page_render)
                
            page_num += 1
        week_num += 1

def generate_user_html(conn, cursor):
    user_template = Template(codecs.open('templates/user_template.html', 'r+', encoding='utf-8').read())
        
    cursor.execute('SELECT user, COUNT(DISTINCT url) AS num_posts FROM screenshots GROUP BY user ORDER by num_posts DESC;')
    users = cursor.fetchall()
    avatars_loaded = 0
    for user_name in users:
        user_name = user_name[0]
        print 'Writing user page %s' % user_name
        cursor.execute('select distinct user, tweet_text, url from screenshots where user=? order by ts desc', (user_name,))
        screenshots = cursor.fetchall()
        context_dict = {'screenshots': screenshots, 'user_name': user_name}
        
        context = Context(context_dict)
        page_render = user_template.render(context)
        
        f = codecs.open('user/%s.html' % user_name, 'w+', encoding='utf-8')
        f.write(page_render)
        
        if avatars_loaded < 10 and not os.path.exists('user/%s.avatar' % user_name):
            uo = urllib.urlopen('http://api.twitter.com/1/users/profile_image/%s.json?size=bigger' % user_name)
            f = open('user/%s.avatar' % user_name, 'w+b')
            f.write(uo.read())
            f.close()
            
            avatars_loaded += 1
    
    users_template = Template(codecs.open('templates/users_template.html', 'r+', encoding='utf-8').read())
    
    page_render = users_template.render(Context({'users': users}))
    
    f = codecs.open('users.html', 'w+', encoding='utf-8')
    f.write(page_render)
        
def main():    
    conn = sqlite3.connect(sqlite_db)
    
    cursor = conn.cursor()
    
    create_db(conn, cursor)
    get_tweets(conn, cursor)
    download_images(conn, cursor)
    generate_thumbnails()
    delete_duplicates(conn, cursor)
        
    generate_gallery_html(conn, cursor)
    generate_user_html(conn, cursor)

    conn.close()

if __name__ == '__main__':
    main()
