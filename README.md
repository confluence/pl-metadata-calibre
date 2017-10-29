# pl-metadata-calibre
Polish-language metadata source plugin(s) for Calibre

This is a collection of metadata source plugins for various Polish online bookstores, selected completely unscientifically on the basis of the success of a particular ISBN test search. I may extend the list in the future. Suggestions and pull requests welcome, with the caveat that I have no plans to implement plugins for arbitrary online stores which don't have well-formed metadata specific to books.

## Plugins:

* `pwn-calibre` for ksiegarnia.pwn.pl (IN PROGRESS)
* `bonito-calibre` for bonito.pl (TODO)
* `livro-calibre` for livro.pl (TODO)
* `wersalik-calibre` for wersalik.pl (TODO)

## Installation instructions (Linux and Mac; Windows should be similar):

These are all separate plugins which need to be installed separately.

    # clone repository
    git clone https://github.com/confluence/pl-metadata-calibre.git
    
    # navigate to the parent directory
    cd pl-metadata-calibre
    
    # add the plugin(s) to calibre
    calibre-customize -b pwn-calibre
    # repeat for each plugin you want to install
    
