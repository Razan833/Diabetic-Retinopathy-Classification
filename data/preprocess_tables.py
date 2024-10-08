from os import listdir
from os.path import isfile, join
import pandas as pd
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--dataset_name', type=str, default="DDR", help='Name of available dataset')
parser.add_argument('--root_dir', type=str, default="local_datasets", help='Name of available dataset')

datasets_info = {"DDR": {"dataset_name": "DDR-dataset", "folder_prefix": "DR_grading"}}

def main():
    args = parser.parse_args()
    dataset_name = datasets_info[args.dataset_name]["dataset_name"]
    folder_prefix = datasets_info[args.dataset_name]["folder_prefix"]
    root_dir = args.root_dir

    subset_names = ["test", "train", "valid"]

    for subset_name in subset_names:
        print(f'Subset {subset_name}: ')
        path = root_dir+"/"+dataset_name+'/'+folder_prefix+"_processed/"+subset_name
        init_filename = root_dir+"/"+dataset_name+'/'+folder_prefix+"/" + subset_name + ".txt"
        output_filename = root_dir+"/"+dataset_name+'/'+folder_prefix+"/" + subset_name + ".csv"

        image_files = [f for f in listdir(path) if isfile(join(path, f))]

        data = pd.read_csv(init_filename, sep=" ", header=None)
        data.columns = ["image_path", "label"]

        image_paths = data["image_path"].to_list()
        labels = data["label"].to_list()

        processed_cntr = 0
        failed_cntr = 0

        new_image_paths = []
        new_labels = []


        for i, image_path in enumerate(image_paths):
            if image_path not in image_files:
                failed_cntr += 1
            else:
                processed_cntr += 1
                new_image_paths.append(image_path)
                new_labels.append(labels[i])
                
        print("Processed successufly: ", processed_cntr)
        print("Processing failed: ", failed_cntr)

        new_dataset = {"image_path": new_image_paths, "label": new_labels}
        new_dataset = pd.DataFrame().from_dict(new_dataset)
        new_dataset.to_csv(output_filename)

if __name__ == '__main__':
    main()

