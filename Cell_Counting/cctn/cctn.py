#============================================================================================
# Cell Counting in Target Nuclei Script
# Author: Gerald M
#
# This script performs automated cell counting in anatomical structures of interest, or a
# a stack of TIFFs. It works by first determining an ideal threshold based on the circularity
# of objects. Then by tracking cells/objects over multiple layers to account for oversampling.
# The output provides a list of coordinates for identified cells. This should then be fed
# into the image predictor to confirm whether objects are cells or not.
#
# Instructions:
# 1) Run the script in a Python IDE
#============================================================================================

################################################################################
## Module import
################################################################################

import os, time, numpy, math, json, warnings, csv
import numpy as np
import nibabel as nib
import matplotlib.pyplot as plt
import scipy.misc as sc
from filters.gaussmedfilt import gaussmedfilt
from filters.medfilt import medfilt
from filters.circthresh import circthresh
from skimage.measure import regionprops, label
from PIL import Image
from skimage import io
from natsort import natsorted

os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
warnings.simplefilter('ignore', Image.DecompressionBombWarning)
Image.MAX_IMAGE_PIXELS = 1000000000

################################################################################
## Function definitions
################################################################################

def distance(a, b):
    return (a[0] - b[0])**2  + (a[1] - b[1])**2

def get_children(json_obj, ids):
    for obj in json_obj:
        if obj['children'] == []:
            ids.append(obj['id'])
        else:
            get_children(obj['children'], ids)
    return ids

def get_structure(json_obj, acronym):
    found = (False, None)
    for obj in json_obj:
        if obj['acronym'].lower() == acronym:
            #print obj['acronym'], obj['id']
            ids = get_children(obj['children'], [])
            #print ids
            if ids == []:
                ids = [obj['id']]
                return (True, ids)
            else:
                ids.append(obj['id'])
                return (True, ids)
        else:
            found = get_structure(obj['children'], acronym)
            if found:
                return found

if __name__ == '__main__':
    ################################################################################
    ## User defined parameters
    ################################################################################

    # Scale the data set to check if everything is the same
    downsize = .5 #1.

    # Fill in the following details to choose the analysis parameters
    mask = True
    over_sample = True
    xy_res = 10
    z_res = 5

    # Fill in structure_list using acronyms and separating structures with a ','
    # E.g. 'LGd, LGv, IGL, RT'
    if mask:
        structure_list = 'lgd'#,LGv,IGL,RT,LP,VPM,VPL,APN,ZI,LD'

    # Cell descriptors
    size = 200.*(downsize**2)
    radius = 12.*downsize

    # Directory of files to count
    #count_path = raw_input('Image path (drag-and-drop): ').rstrip()
    count_path = '/mnt/BrickleyLab/TissueCyte/Sox14/Gerald_170127_Sox14_HET2/het2-Mosaic/Ch2_Stitched_Sections'
    # Number of files [None,None] for all, or [start,end] for specific range
    number_files = [1,1000]

    ################################################################################
    ## Initialisation parameters
    ################################################################################

    # List of files to count
    count_files = []
    count_files += [each for each in os.listdir(count_path) if each.endswith('.tif')]
    count_files = natsorted(count_files)
    if number_files[0] != None:
        count_files = count_files[number_files[0]-1:number_files[1]]
    print 'Counting in files: '+count_files[0]+' to '+count_files[-1]

    ################################################################################
    ## Retrieving structures IDs
    ################################################################################

    if mask:
        #path = raw_input('NII/TIFF file path (drag-and-drop): ').rstrip()
        path = '/mnt/BrickleyLab/TissueCyte/Sox14/Gerald_170127_Sox14_HET2/het2-Mosaic/SEGMENTATION_RES.tif'
        file, extension = os.path.splitext(path)
        if extension == '.nii':
            seg = nib.load(path).get_data()
        else:
            seg = io.imread(path)
        print 'Loaded segmentation data'

    ids = []
    if mask:
        anno_file = json.load(open('2017_annotation_structure_info.json'))
        structure_list = structure_list.lower().split(",")
        for elem in structure_list:
            ids.append(np.array(get_structure(anno_file['children'], elem)[1]))
    else:
        ids.append('none')
    print 'Counting in structures: '+str(structure_list)

    ################################################################################
    ## Counting
    ################################################################################

    tstart = time.time()

    # Dictionary to store centroids - each key is a new slice number
    total_cells = dict()

    temp = Image.open(count_path+'/'+count_files[0])
    temp_size = temp.size
    temp = None
    if mask:
        scale = float(temp_size[1])/seg[1].shape[0]

    structure_index = 0

    for structure in ids:
        print 'Counting in '+str(structure_list[structure_index])
        ################################################################################
        ## Obtain crop information for structure if mask required
        ################################################################################
        if mask:
            index = np.array([[],[],[]])
            for elem in structure:
                if elem in seg:
                    index = np.concatenate((index, np.array(np.nonzero(elem == seg))), axis=1)
                else:
                    structure = np.setdiff1d(structure, elem)

            zmin = int(index[0].min())
            zmax = int(index[0].max())
            ymin = int(index[1].min()*scale*downsize)
            ymax = int(index[1].max()*scale*downsize)
            xmin = int(index[2].min()*scale*downsize)
            xmax = int(index[2].max()*scale*downsize)
        else:
            zmin = 0
            zmax = len(count_files)
            ymin = 0
            ymax = temp_size[1]*downsize
            xmin = 0
            xmax = temp_size[0]*downsize

        ################################################################################
        ## Loop through slices based on cropped boundaries
        ################################################################################
        for slice_number in range(zmin,zmax):
            # Load image and convert to dtype=float
            image = Image.open(count_path+'/'+count_files[slice_number])
            image = np.array(image.resize(tuple([int(downsize*x) for x in temp_size]), Image.NEAREST))[ymin:ymax, xmin:xmax]
            image = np.multiply(np.divide(image,65535.), 255.)

            # Apply mask if required
            if mask:
                mask_image = np.array(Image.fromarray(seg[slice_number]).resize(tuple([int(downsize*x) for x in temp_size]), Image.NEAREST))[ymin:ymax, xmin:xmax]
                mask_image[mask_image!=structure] = 0
                image[mask_image==0] = 0
                print np.max(image)
                mask_image = None
                #Image.fromarray(np.uint8(image)*255).save('/home/gm515/Documents/Temp4/Z_'+str(slice_number)+'.tif')

            # Perform gaussian donut median filter
            image = gaussmedfilt(image, 3, 1.5)

            if np.max(image) != 0.:
                image = np.multiply(np.divide(image, np.max(image)), 255.)

                # Perform circularity threshold
                image = image>circthresh(image,size,50)
                Image.fromarray(np.uint8(image)*255).save('/home/gm515/Documents/Temp3/Z_'+str(slice_number)+'.tif')

                # Remove objects smaller than chosen size
                image_label = label(image, connectivity=image.ndim)

                circfunc = lambda r: (4 * math.pi * r.area) / ((r.perimeter * r.perimeter) + 0.00000001)

                circ = [circfunc(region) for region in regionprops(image_label)]
                areas = [region.area for region in regionprops(image_label)]
                labels = [region.label for region in regionprops(image_label)]
                centroids = [region.centroid for region in regionprops(image_label)]

                #image = np.zeros_like(image_label)

                # Threshold the objects based on size and circularity and store centroids
                cells = []
                for i, _ in enumerate(areas):
                    if areas[i] > size/2 and areas[i] < size*4 and circ[i] > 0.65:
                        # (row, col) centroid
                        cells.append(centroids[i])
                        #image += image_label==labels[i]
            else:
                cells = []

            total_cells.update({slice_number : cells})

            print 'Analysed slice '+str(slice_number)

            #image = image>0 # Create image if needed
            #Image.fromarray(np.uint8(image)*255).save('/Users/gm515/Desktop/temp/Z_'+str(slice_number)+'.tif')


        # Peform correction for overlap
        if over_sample:
            print 'Correcting for oversampling'
            for idx, (x, y) in enumerate(zip(total_cells.values()[1:], total_cells.values()[:-1])):
                if len(x) * len(y) > 0:
                    total_cells[zmin+idx] = [ycell for ycell in y if all(distance(xcell,ycell)>radius**2 for xcell in x)]

        num_cells = sum(map(len, total_cells.values()))

        print structure_list[structure_index]+' '+str(num_cells)

        csv_file = structure_list[structure_index]+'_count.csv'
        with open(csv_file, 'w+') as f:
            for key in total_cells.keys():
                if len(total_cells[key])>0:
                    csv.writer(f, delimiter=',').writerows(np.round(np.concatenate((np.ones((len(total_cells[key]), 1))*(key+1), [( (np.array(val) + np.arrray([xmin, ymin]))/downsize).tolist() for val in total_cells[key]]), axis=1)))

        structure_index += 1

    print '~Fin~'

    minutes, seconds = divmod(time.time()-tstart, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    print 'Counting completed in %02d:%02d:%02d:%02d' %(days, hours, minutes, seconds)
