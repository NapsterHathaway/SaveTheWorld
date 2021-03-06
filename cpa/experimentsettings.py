from singleton import Singleton
from utils import *
import re
from timeline import Timeline

#
# TODO: Updating PlateDesign could be done entirely within 
#       set_field and remove_field.
#
# TODO: Add backwards compatiblize and file versioning.
#

def format_time_string(timepoint):
    '''formats the given time as a string
    '''
    hours = int(timepoint) / 60
    mins = timepoint - 60 * hours
    return '%s:%02d'%(hours, mins)

def get_matchstring_for_subtag(pos, subtag):
    '''matches a subtag at a specific position.
    '''
    return '([^\|]+\|){%s}%s.*'%(pos, subtag)

def get_tag_stump(tag, n_subtags=3):
    return '|'.join(tag.split('|')[:n_subtags])

def get_tag_attribute(tag):
    return tag.split('|')[2]

def get_tag_instance(tag):
    return tag.split('|')[3]

def get_tag_timepoint(tag):
    return int(tag.split('|')[4])

def get_tag_well(tag):
    '''Returns the well subtag from image tags of the form:
    DataAcquis|<type>|Images|<inst>|<timepoint>|<well> = [channel_urls, ...]
    '''
    return int(tag.split('|')[5])

def get_tag_protocol(tag):
    '''returns the tag prefix and instance that define a unique protocol
    eg: get_tag_protocol("CT|Seed|Density|1") ==> "CT|Seed|1"
    '''
    return get_tag_stump(tag,2) + '|' + tag.split('|')[3]


class ExperimentSettings(Singleton):
    
    global_settings = {}
    timeline        = Timeline('TEST_STOCK')
    subscribers     = {}
    
    def __init__(self):
        pass
    
    def set_field(self, tag, value, notify_subscribers=True):
        self.global_settings[tag] = value
        if re.match(get_matchstring_for_subtag(2, 'Well'), tag):
            self.update_timeline(tag)
        if notify_subscribers:
            self.notify_subscribers(tag)
        print 'SET FIELD: %s = %s'%(tag, value)
        
    def get_field(self, tag, default=None):
        return self.global_settings.get(tag, default)

    def remove_field(self, tag, notify_subscribers=True):
        '''completely removes the specified tag from the metadata (if it exists)
        '''
        #if self.get_field(tag) is not None:
        self.global_settings.pop(tag)
        if re.match(get_matchstring_for_subtag(2, 'Well'), tag):
            self.update_timeline(tag)

        if notify_subscribers:
            self.notify_subscribers(tag)
        print 'DEL FIELD: %s'%(tag)
    
    def get_action_tags(self):
        '''returns all existing TEMPORAL tags as list'''
        return [tag for tag in self.global_settings 
                if tag.split('|')[0] in ('CellTransfer', 'Perturbation', 
                                    'Labeling', 'AddProcess', 'DataAcquis')]

    def get_field_instances(self, tag_prefix):
        '''returns a list of unique instance ids for each tag beginning with 
        tag_prefix'''
        ids = set([get_tag_instance(tag) for tag in self.global_settings
                   if tag.startswith(tag_prefix)])
        return list(ids)
    
    def get_attribute_list(self, tag_prefix):
        '''returns a list of attributes name for each tag beginning with 
        tag_prefix'''
        ids = set([get_tag_attribute(tag) for tag in self.global_settings
                   if tag.startswith(tag_prefix)])
        return list(ids)
    
    def get_attribute_dict(self, protocol):
        '''returns a dict mapping attribute names to their values for a given
        protocol.
        eg: get_attribute_dict('CellTransfer|Seed|1') -->
               {'SeedingDensity': 12, 'MediumUsed': 'agar', 
                'MediumAddatives': 'None', 'Trypsinization': True}
        '''
        d = {}
        for tag in self.get_matching_tags('|*|'.join(protocol.rsplit('|',1))):
            if (get_tag_attribute(tag) not in ('Wells', 'EventTimepoint', 'Images', 'OriginWells')):
                d[get_tag_attribute(tag)] = self.global_settings[tag]
        return d
    
    def get_eventtype_list(self, tag_prefix):
        '''returns a list of attributes name for each tag beginning with 
        tag_prefix'''
        ids = set([tag.split('|')[1] for tag in self.global_settings
                   if tag.startswith(tag_prefix)])
        return list(ids)
    
    def get_eventclass_list(self, tag_prefix):
        '''returns a list of event class name for each tag beginning with 
        tag_prefix'''
        ids = set([tag.split('|')[0] for tag in self.global_settings
                   if tag.startswith(tag_prefix)])
        return list(ids)

    def get_field_tags(self, tag_prefix=None, instance=None):
        '''returns a list of all tags beginning with tag_prefix. If instance
        is passed in, only tags of the given instance will be returned'''
        tags = []
        for tag in self.global_settings:
            if ((tag_prefix is None or tag.startswith(tag_prefix)) and 
                (instance is None or get_tag_instance(tag) == instance)):
                tags += [tag]
        return tags
    
    def get_matching_tags(self, matchstring):
        '''returns a list of all tags matching matchstring
        matchstring -- a string that matches the tags you want
        eg: CellTransfer|*
        '''
        tags = []
        for tag in self.global_settings:
            match = True
            for m, subtag in map(None, matchstring.split('|'), tag.split('|')):
                if m != subtag and m not in ('*', None):
                    match = False
                    break
            if match:
                tags += [tag]

        return tags
    
    def get_protocol_instances(self, prefix):
        '''returns a list of protocol instance names for tags 
        matching the given prefix.
        '''
        return list(set([get_tag_instance(tag) 
                         for tag in self.get_field_tags(prefix)]))
    
    def get_new_protocol_id(self, prefix):
        '''returns an id string that hasn't been used for the given tag prefix
        prefix -- eg: CellTransfer|Seed
        '''
        instances = self.get_protocol_instances(prefix)
        for i in xrange(1, 100000):
            if str(i) not in instances:
                return str(i)
    
    def clear(self):
        self.global_settings = {}
        PlateDesign.clear()
        #
        # TODO:
        #
        self.timeline = Timeline('TEST_STOCK')
        for matchstring, callbacks in self.subscribers.items():
            for callback in callbacks:
                callback(None)
        
    def get_timeline(self):
        return self.timeline

    def update_timeline(self, welltag):
        '''Updates the experiment metadata timeline event associated with the
        action and wells in welltag (eg: 'ExpNum|AddProcess|Spin|Wells|1|1')
        '''
        platewell_ids = self.get_field(welltag, [])
        if platewell_ids == []:
            self.timeline.delete_event(welltag)
        else:
            event = self.timeline.get_event(welltag)
            if event is not None:
                event.set_well_ids(platewell_ids)
            else:
                self.timeline.add_event(welltag, platewell_ids)

    def save_to_file(self, file):
        f = open(file, 'w')
        for field, value in sorted(self.global_settings.items()):
            f.write('%s = %s\n'%(field, repr(value)))
        f.close()

    def load_from_file(self, file):
        # Populate the tag structure
        self.clear()
        f = open(file, 'r')
        for line in f:
            tag, value = line.split('=')
            tag = tag.strip()
            self.set_field(tag, eval(value), notify_subscribers=False)
        f.close()
        
        # Populate PlateDesign
        PlateDesign.clear()
        for vessel_type in ('Plate', 'Flask', 'Dish', 'Coverslip'):
            prefix = 'ExptVessel|%s'%(vessel_type)
            for inst in self.get_field_instances(prefix):
                d = self.get_attribute_dict(prefix+'|'+inst)
                shape = d.get('Design', None)
                if shape is None:
                    shape = (1,1)
                group = d.get('GroupName', None)
                PlateDesign.add_plate(vessel_type, inst, shape, group)
            
        # Update everything
        for tag in self.global_settings:
            self.notify_subscribers(tag)            

        # Update the bench time-slider
        # TODO: this is crappy
        try:
            import wx
            bench = wx.GetApp().get_bench()
            bench.set_time_interval(0, self.get_timeline().get_max_timepoint())
        except:return
                
    def add_subscriber(self, callback, match_string):
        '''callback -- the function to be called
        match_string -- a regular expression string matching the tags you want 
                        to be notified of changes to
        '''
        self.subscribers[match_string] = self.subscribers.get(match_string, []) + [callback]
        
    def remove_subscriber(self, callback):
        '''unsubscribe the given callback function.
        This MUST be called before a callback function is deleted.
        '''
        for k, v in self.subscribers:
            if v == callback:
                self.subscribers.pop(k)
            
    def notify_subscribers(self, tag):
        for matchstring, callbacks in self.subscribers.items():
            if re.match(matchstring, tag):
                for callback in callbacks:
                    callback(tag)


ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

# Plate formats
FLASK = (1, 1)
#P1    = (1,1)
#P2    = (1,2)
#P4    = (1,4)
P6    = (2, 3)
#P8    = (2,4)
P12   = (3,4)
P24   = (4, 6)
P48   = (6, 8)
P96   = (8, 12)
P384  = (16, 24)
P1536 = (32, 48)
P5600 = (40, 140)

WELL_NAMES = {
              #'1-Well-(1x1)'       : P1,
              #'2-Well-(1x2)'       : P2,
              #'4-Well-(1x4)'       : P4,
              '6-Well-(2x3)'       : P6,
              #'8-Well-(2x4)'       : P8,
              '12-Well-(3x4)'      : P12, 
              '24-Well-(4x6)'      : P24, 
              '48-Well-(6x8)'      : P48,
              '96-Well-(8x12)'     : P96, 
              '384-Well-(16x24)'   : P384, 
              '1536-Well-(32x48)'  : P1536, 
              '5600-Well-(40x140)' : P5600,
              }

WELL_NAMES_ORDERED = [
                      #'1-Well-(1x1)',
                      #'2-Well-(1x2)',
                      #'4-Well-(1x4)',
                      '6-Well-(2x3)',
                      #'8-Well-(2x4)',
                      '12-Well-(3x4)',
                      '24-Well-(4x6)',
                      '48-Well-(6x8)',
                      '96-Well-(8x12)',
                      '384-Well-(16x24)',
                      '1536-Well-(32x48)',
                      '5600-Well-(40x140)']


class Vessel(object):
    def __init__(self, vessel_type, instance, shape, group, **kwargs):
        self.instance    = instance
        self.group       = group
        self.vessel_type = vessel_type
        if type(shape) == tuple:
            self.shape = shape
        else:
            self.shape = WELL_NAMES[shape]
##        meta.set_field('ExptVessel|%(vessel_type)|Design|%(instance)'%(locals), shape)
##        meta.set_field('ExptVessel|%(vessel_type)|GroupName|%(instance)'%(locals), group)
        for k,v in kwargs:
            self.set_attribute(k, v)
        
##    def __del__(self):
##        for tag in meta.get_matching_tags('ExptVessel|%(vessel_type)|*|%(instance)'%(self.__dict__)):
##            meta.remove_field(tag)
            
    def set_attribute(self, att, value):
        self.__dict__[att] = value
##        meta.set_field('ExptVessel|%s|*|%s'%(att, self.instance), value)
        
    @property
    def vessel_id(self):
        return '%(vessel_type)s%(instance)s'%(self.__dict__)    


class PlateDesign:
    '''Maps plate_ids to plate formats.
    Provides methods for getting well information for different plate formats.
    '''
    
    plates = {}
    
    @classmethod
    def clear(self):
        self.plates = {}
        
    @classmethod
    def add_plate(self, vessel_type, instance, shape, group, **kwargs):
        '''Add a new plate with the specified format
        '''
        v = Vessel(vessel_type, instance, shape, group, **kwargs)
        self.plates[v.vessel_id] = v
        
    @classmethod
    def set_plate_format(self, plate_id, shape):
        self.plates[plate_id].shape = shape
        
    @classmethod
    def get_plate_ids(self):
        return self.plates.keys()
    
    @classmethod
    def get_plate_id(self, vessel_type, instance):
        for vessel in self.plates.values():
            if vessel.instance == instance and vessel.vessel_type == vessel_type:
                return vessel.vessel_id
            
    @classmethod
    def get_plate_group(self, vessel_id):
        return self.plates[vessel_id].group
    
    @classmethod
    def get_vessel(self, vessel_id):
        return self.plates[vessel_id]

    @classmethod
    def get_plate_format(self, plate_id):
        '''returns the plate_format for a given plate_id
        '''
        return self.plates[plate_id].shape
    
    @classmethod
    def get_all_platewell_ids(self):
        '''returns a list of every platewell_id across all plates
        '''
        return [(plate_id, well_id) 
                for plate_id in self.plates
                for well_id in self.get_well_ids(self.get_plate_format(plate_id))
                ]

    @classmethod
    def get_well_ids(self, plate_format):
        '''plate_format - a valid plate format. eg: P96 or (8,12)
        '''
        return ['%s%02d'%(ch, num) 
                for ch in ALPHABET[:plate_format[0]] 
                for num in range(1,plate_format[1]+1)]
    
    @classmethod
    def get_col_labels(self, plate_format):
        return ['%02d'%(num) for num in range(1,plate_format[1]+1)]

    @classmethod
    def get_row_labels(self, plate_format):
        return list(ALPHABET[:plate_format[0]])
    
    @classmethod
    def get_well_id_at_pos(self, plate_format, (row, col)):
        assert 0 <= row < plate_format[0], 'invalid row %s'%(row)
        assert 0 <= col < plate_format[1], 'invalid col %s'%(col)
        cols = plate_format[1]
        return PlateDesign.get_well_ids(plate_format)[cols*row + col]

    @classmethod
    def get_pos_for_wellid(self, plate_format, wellid):
        '''returns the x,y position of the given well
        eg: get_pos_for_wellid(P96, 'A02') --> (0,1)
        '''
        if type(wellid) is tuple:
            wellid = wellid[-1]
        row = ALPHABET.index(wellid[0])
        col = int(wellid[1:]) - 1
        assert row < plate_format[0] and col < plate_format[1], 'Invalid wellid (%s) for plate format (%s)'%(wellid, plate_format)
        return (row, col)