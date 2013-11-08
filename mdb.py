import sys;
from bs4 import BeautifulSoup;
import urllib.request
import re;
import base64;
import os;

#config

#the file used for output
outFile = 'out.sql';

#the maximum number of award categories to get for each movie
maxAwardCategories = 3;

#endconfig

movies = [];
actors = [];
awards = [];

#lookup a webpage (first in the cache, then online)
def fetchPage(pageUrl):
    ##check cache
    cacheFolder = "webcache";
    #filename is base64 encoded url of the page
    cachePath = cacheFolder + "\\" + str(base64.urlsafe_b64encode(bytes(pageUrl, 'ascii')));
    if not os.path.exists(cacheFolder): #check for cache dir
        os.makedirs(cacheFolder);
    else:
        if os.path.exists(cachePath):
            with open(cachePath, 'rb') as f:
                return f.read();

    ##not cached => download it
    req = urllib.request.Request(pageUrl, headers={'User-Agent' : "Firefox 3.3"});
    response = urllib.request.urlopen(req);
    page = response.read();
    with open(cachePath, 'wb') as f:    #save it
        f.write(page);

    return page;

#get a movie's IMDb soup
def getImdbSoup(movieId, pageid):
    url = "http://www.imdb.com/title/tt" + movieId + "/" + pageid;
    html = fetchPage(url);
    return BeautifulSoup(str(html));

#quickfix for string cleanup and unicode unescaping
def fix(str):
    return str.encode().decode('unicode-escape').replace("'", '"').replace('\\', '');

scrapedMovies = set();
#scrapes a movie with a given id
def scrapeMovie(id):
    #check if already added
    if id in scrapedMovies:
       return;
    scrapedMovies.add(id);

    ##soups
    print(str(id), end = '\t');
    movieSoup = getImdbSoup(id, '');
    creditsSoup = getImdbSoup(id, 'fullcredits');
    businessSoup = getImdbSoup(id, 'business');
    awardsSoup = getImdbSoup(id, 'awards');

    ##movie
    #title, year
    titleYearRegex = "^(.+) \((\d+)\) - IMDb$";
    ty = re.search(titleYearRegex, movieSoup.title.string).groups(0);
    title = fix(ty[0]);
    #print(str(title));
    year = int(ty[1]);
    #director
    director = fix(movieSoup.find(itemprop='director').find(itemprop='name').text);
    #rating
    rating = float(movieSoup.find("div", { "class" : "titlePageSprite star-box-giga-star" }).text);
    #country
    country = fix(movieSoup.find("a", href = re.compile('^/country/')).text);
    #genre
    genre = fix(movieSoup.find("span", { "itemprop": "genre" }).text);
    #producer
    prodtd = creditsSoup.find('td', class_='credit', text=re.compile(r'^( |\\n)*(p|P)roduc(er|tion)( |\\n)+'));
    if prodtd == None:
        prodtd = creditsSoup.find('td', class_='credit', text=re.compile(r'^( |\\n)*(e|E)xecutive (p|P)roducer( |\\n)+'));
    if prodtd == None:
        prodtd = creditsSoup.find('td', class_='credit', text=re.compile(r'^( |\\n)*(a|A)ssociate (p|P)roducer( |\\n)+'));
    prodtr = prodtd.parent;
    producer = fix(prodtr.find('td').a.text).strip();
    #gross
    gross = 0;
    grossRegex = re.compile(r'\\n[\$£€]([0-9]{1,3}(,[0-9]{3})*) *\([a-zA-Z]+\)');
    grossVals = businessSoup.find_all(text=grossRegex);
    for grossVal in grossVals:  #just grab the max value in USD or GBP or EUR
        sVal = ''.join(c for c in grossRegex.match(grossVal).groups(0)[0] if c.isdigit());
        val = int(sVal);
        #currency conversion, lmao
        if grossVal.strip()[0] == '£':
            val = int(val * 1.6);
        elif grossVal.strip()[0] == '€':
            val = int(val * 1.35);
        if val > gross:
            gross = val;

    ##awards
    scrapeAwards(awardsSoup, title, year);

    ##actors
    actorTable = movieSoup.find(class_='cast_list');
    for actT in actorTable.find_all("tr"):
        actorName = actT.find(itemprop='name');
        charName = actT.find("td", { "class" : "character" });

        if actorName != None and charName != None:
            actorName = fix(actorName.text);
            charName = charName.text;
            charName = re.sub(r'(\\n| )+', ' ', charName);           #filter excessive space
            charName = fix(re.sub(r'\(as .{1,30}\)', '', charName).strip());     #filter listed as explanation "(as Listed)"
            #print('charName: "' + charName + '"');
            #add to table
            act = (title, year, actorName, charName);
            actors.append(act);

    ##add to table
    mov = (title, year, director, country, rating, genre, gross, producer);
    movies.append(mov);
    print("done");

#scrapes a movie's awards
def scrapeAwards(soup, title, year):
    awset = set();  #no shared awards (must be unique!)
    for table in soup.find_all("table", class_ = "awards")[:maxAwardCategories]: #limit to first n tables
        curType = ""
        curOutcome = ""
        for row in table.find_all("tr"):
            section = row.find("td", class_ = "title_award_outcome");
            if(section != None):    #no new category/win means we use the previous one
                curOutcome = section.find('b').text.lower();
                curType = section.find('span').text;
            if(curOutcome != 'won' and curOutcome != 'nominated'):  #wth, ignore those
                continue;
            taward = row.find("td", { "class" : "award_description" });
            awardDesc = re.match(r'^ *\\n *([a-zA-Z].+?) *\\n *', taward.text);
            if awardDesc != None:
                award = fix(curType + ", " + awardDesc.groups(0)[0]);
            else:
                award = fix(curType);


            if not award in awset:
                awset.add(award);
                aw = (title, year, award, curOutcome);
                awards.append(aw);

#saves the collected data to the out file
def saveResults():
    print('Saving results.. ', end = '');
    
    #does open 'w' make a new file?
    if os.path.exists(outFile):
        os.remove(outFile);
    
    s = 0;

    with open(outFile, "w", encoding='utf-8') as f:
        mTotal = len(movies);
        aTotal = len(actors);
        awTotal = len(awards);
        mDone = 0;
        aDone = 0;
        awDone = 0;

        #print movies
        f.write('INSERT INTO Movies VALUES\n');
        for m in movies:
            try:
                f.write("\t('%s', %d, '%s', '%s', %1.1f, '%s', %d, '%s')" % m);
                mDone = mDone + 1;
            except:
                err = 1;
            if m == movies[mTotal - 1]:
                f.write(';\n');
            else:
                f.write(',\n');
        #print actors
        f.write("INSERT INTO Actors VALUES\n");
        for a in actors:
            try:
                f.write("\t('%s', '%s', '%s', '%s')" % a);
                aDone = aDone + 1;
            except:
                err = 1;
            if a == actors[aTotal - 1]:
                f.write(';\n');
            else:
                f.write(',\n');
        #print awards
        f.write("INSERT INTO Awards VALUES\n");
        for aw in awards:
            try:
                f.write("\t('%s', %d, '%s', '%s')" % aw);
                awDone = awDone + 1;
            except:
                err = 1;
            if aw == awards[awTotal - 1]:
                f.write(';\n');
            else:
                f.write(',\n');

    print('done! (%d/%d movies, %d/%d actors, %d/%d awards)' % (mDone, mTotal, aDone, aTotal, awDone, awTotal));

def scrapePageForLinks(url):
    print("Opening '%s'" % url, end = '');
    
    #get page, soup
    topPage = fetchPage(url);
    soup = BeautifulSoup(topPage);
    
    #get the titles chart
    table = soup.find("table", class_ = "chart");
    tbody = soup.find("tbody");
    
    print(' done!');

    #search for all links to movies
    top_regex = "/title/tt([0-9]{7})/.+";
    ids = set();    #ignore duplicates
    for link in soup.find_all(href = re.compile(top_regex)):    #find them links to movies
        addr = link.get('href');
        id = re.match(top_regex, addr).groups(0)[0];
        if not id in ids:
            ids.add(id);
            print(str(len(ids)), end = '. ');
            scrapeMovie(str(id));  #do the work

def main():
    if len(sys.argv) > 1:   #args
        for argurl in sys.argv[1:]:
            try:
                scrapePageForLinks(v);
            except:
                print("Something went wrong at %s" % argurl);
    else:   #cli
        url = '';
        while True:
            #get url/command
            url = input("Enter an url to scrape, leave blank for IMDb Top 250 page, or type 'quit' to save and exit: ");
            if url == 'quit':
                break;
            if len(url.strip()) == 0:
                url = "http://www.imdb.com/chart/top";

            #try scraping the page
            try:
                scrapePageForLinks(url);
            except:
                print("Woops, something went wrong!");

            print("%d movies scraped so far" % len(movies));
    saveResults();

main();
