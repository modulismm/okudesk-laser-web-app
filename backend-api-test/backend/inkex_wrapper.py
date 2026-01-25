"""
Wrapper pour simuler l'API Inkscape (inkex)
Permet d'utiliser les scripts Inkscape sans Inkscape installé

Ce wrapper doit implémenter les fonctions/classes utilisées par:
- 2.1_Nomadtech-OkuDesk_Contornos.py
- 2.1_Nomadtech-OkuDesk_Raster.py
"""

from lxml import etree
import sys

class MockInkscapeExtension:
    """
    Simule la classe inkex.Effect utilisée par les extensions Inkscape
    """
    
    def __init__(self, svg_content):
        """
        Args:
            svg_content: Contenu SVG en string
        """
        # Parse SVG avec lxml
        self.document = etree.fromstring(svg_content.encode('utf-8'))
        
        # Simuler les options (normalement venant de l'interface Inkscape)
        self.options = type('Options', (object,), {
            'feed': 1000,           # Vitesse par défaut
            'laser_power': 100.0,   # Puissance par défaut
            'passes': 1             # Nombre de passes
        })()
        
        # Variables pour le frame/bounds
        self.minXforFrame = 0
        self.maxXforFrame = 0
        self.minYforFrame = 0
        self.maxYforFrame = 0
        
        # Temps estimé
        self.estimatedTime = 0
    
    def get_by_id(self, id, listofobjects=None):
        """
        Simule get_by_id() des scripts Inkscape
        Trouve un élément par son ID dans le SVG
        """
        if listofobjects is None:
            listofobjects = self.document.getchildren()
        
        for element in listofobjects:
            if element.get("id") == id:
                return element
            elif element.tag.endswith("g"):  # Groupe SVG
                found = self.get_by_id(id, element.getchildren())
                if found is not None:
                    return found
        
        return None
    
    def getroot(self):
        """Retourne la racine du document"""
        return self.document


# Simuler le module inkex
class MockInkex:
    """Module inkex simulé"""
    
    @staticmethod
    def errormsg(msg):
        """Affiche un message d'erreur"""
        print(f"ERROR: {msg}", file=sys.stderr)
    
    @staticmethod
    def addNS(tag, namespace):
        """Ajoute un namespace à un tag"""
        return f"{{{namespace}}}{tag}"


# Injecter dans sys.modules pour que les imports fonctionnent
sys.modules['inkex'] = MockInkex()

# Simuler simplestyle et simplepath
# TODO: Implémenter ces modules si nécessaire
sys.modules['simplestyle'] = type('Module', (), {})()
sys.modules['simplepath'] = type('Module', (), {
    'parsePath': lambda d: [],  # Placeholder
})()


def create_extension_from_svg(svg_content, speed=1000, power=100.0, passes=1):
    """
    Crée une instance MockInkscapeExtension depuis du contenu SVG
    
    Args:
        svg_content: Contenu SVG en string
        speed: Vitesse en mm/min
        power: Puissance laser en %
        passes: Nombre de passes
    
    Returns:
        MockInkscapeExtension: Instance configurée
    """
    extension = MockInkscapeExtension(svg_content)
    extension.options.feed = speed
    extension.options.laser_power = power
    extension.options.passes = passes
    
    return extension
