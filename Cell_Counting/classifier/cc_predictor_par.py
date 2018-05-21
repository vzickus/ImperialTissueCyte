# Perform final correction of cell counts

import os, sys, warnings
import numpy as np
from keras.preprocessing import image
from keras.models import load_model
from PIL import Image
from xml.dom import minidom
from multiprocessing import Pool, cpu_count, Array, Manager
from functools import partial
import tqdm
import csv
from keras.preprocessing import image
from keras.models import load_model

os.environ['TF_CPP_MIN_LOG_LEVEL']='2'
warnings.simplefilter('ignore', Image.DecompressionBombWarning)
Image.MAX_IMAGE_PIXELS = 1000000000

#=============================================================================================
# Define function for predictions
#=============================================================================================

def append_cell(coord):
    cell_markers.append(coord)

def append_nocell(coord):
    nocell_markers.append(coord)

def cellpredict(cell, model_path, marker, image_path, filename, cell_markers, nocell_markers):

    model = load_model(model_path)

    prev_slice = 0
    if prev_slice < marker[cell, 2]:
        #img = image.load_img(os.path.join(image_path, filename[cell]), target_size = (80, 80))
        #img = img.convert('I')
        img = Image.open(os.path.join(image_path, filename[marker[cell, 2]]))
        img = image.img_to_array(img)
        img = np.lib.pad(img, pad_width = ((40, 40), (40, 40), (0, 0)), mode = 'constant', constant_values=0)
        prev_slice = marker[cell, 2]

    # The additional 1230 is a correction from the cropping between the original data and the segmented set - remove as necessary
    cell_crop = img[marker[cell, 1]+1230 : marker[cell, 1]+1230 + 80, marker[cell, 0]+1230 : marker[cell, 0]+1230 + 80]
    #cell_crop = img[marker[cell, 1] : marker[cell, 1] + 80, marker[cell, 0] : marker[cell, 0] + 80]
    cell_crop = np.expand_dims(cell_crop, axis = 0)

    prediction = model.predict(np.asarray(cell_crop))

    if prediction[0][0] == 0: # Cell
        cell_value = 1
        append_cell(marker[cell,:])
        #image.array_to_img(cell_crop[0,:,:,:]).save('/Users/gm515/Desktop/cell_par/'+str(cell)+'.tif')
    else: # No cell
        cell_value = 0
        append_nocell(marker[cell,:])
        #image.array_to_img(cell_crop[0,:,:,:]).save('/Users/gm515/Desktop/nocell_par/'+str(cell)+'.tif')

    result[cell] = cell_value

    return


# Main function
if __name__ == '__main__':

    #=============================================================================================
    # Load CNN classifier model
    #=============================================================================================

    model_path = raw_input('Model file path (drag-and-drop): ').strip('\'').rstrip()

    #=============================================================================================
    # Parameters
    #=============================================================================================

    marker_path = raw_input('XML or CSV file path (drag-and-drop): ').strip('\'').rstrip()

    marker_filename, marker_file_extension = os.path.splitext(marker_path)
    if marker_file_extension == '.xml':
        xml_doc = minidom.parse(marker_path)

        marker_x = xml_doc.getElementsByTagName('MarkerX')
        marker_y = xml_doc.getElementsByTagName('MarkerY')
        marker_z = xml_doc.getElementsByTagName('MarkerZ')

        marker = np.empty((0,3), int)

        for elem in range (0, marker_x.length):
            marker = np.vstack((marker, [int(marker_x[elem].firstChild.data), int(marker_y[elem].firstChild.data), int(marker_z[elem].firstChild.data)]))
    if marker_file_extension == '.csv':
        marker = np.genfromtxt(marker_path, delimiter=',').astype(int)

    #=============================================================================================
    # Load images and correct cell count by predicting
    #=============================================================================================

    image_path = raw_input('Counting file path (drag-and-drop): ').strip('\'').rstrip()
    filename = [file for file in os.listdir(image_path) if file.endswith('.tif')]

    manager = Manager()
    result = Array('i', marker.shape[0])
    cell_markers = manager.list()
    nocell_markers = manager.list()

    cell_index = range(marker.shape[0])

    pool = Pool(cpu_count())
    for _ in tqdm.tqdm(pool.imap_unordered(partial(cellpredict, model_path=model_path, marker=marker, image_path=image_path, filename=filename, cell_markers=cell_markers, nocell_markers=nocell_markers), cell_index), total=marker.shape[0]):
        pass

    #pool.close()
    #pool.join()

    print '\n'
    print 'Correct cell preditions:', result[:].count(1)
    print 'Potential false cell predictions:', result[:].count(0)
