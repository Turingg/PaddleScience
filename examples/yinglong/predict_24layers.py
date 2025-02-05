# Copyright (c) 2023 PaddlePaddle Authors. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
from os import path as osp

import h5py
import numpy as np
import paddle
import pandas as pd
from packaging import version

from examples.yinglong.plot import save_plot_weather_from_dict
from examples.yinglong.predictor import YingLong
from ppsci.utils import logger


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model_file",
        type=str,
        default="./yinglong_models/yinglong_24.pdmodel",
        help="Model filename",
    )
    parser.add_argument(
        "--params_file",
        type=str,
        default="./yinglong_models/yinglong_24.pdiparams",
        help="Parameter filename",
    )
    parser.add_argument(
        "--mean_path",
        type=str,
        default="./hrrr_example_69vars/stat/mean_crop.npy",
        help="Mean filename",
    )
    parser.add_argument(
        "--std_path",
        type=str,
        default="./hrrr_example_69vars/stat/std_crop.npy",
        help="Standard deviation filename",
    )
    parser.add_argument(
        "--input_file",
        type=str,
        default="./hrrr_example_69vars/valid/2022/01/01.h5",
        help="Input filename",
    )
    parser.add_argument(
        "--init_time", type=str, default="2022/01/01/00", help="Init time"
    )
    parser.add_argument(
        "--nwp_file",
        type=str,
        default="./hrrr_example_69vars/nwp_convert/2022/01/01/00.h5",
        help="NWP filename",
    )
    parser.add_argument(
        "--num_timestamps", type=int, default=22, help="Number of timestamps"
    )
    parser.add_argument(
        "--output_path", type=str, default="output_24layers", help="Output file path"
    )

    return parser.parse_args()


def main():
    args = parse_args()
    logger.init_logger("ppsci", osp.join(args.output_path, "predict.log"), "info")
    # log paddlepaddle's version
    if version.Version(paddle.__version__) != version.Version("0.0.0"):
        paddle_version = paddle.__version__
        if version.Version(paddle.__version__) < version.Version("2.6.0"):
            logger.warning(
                f"Detected paddlepaddle version is '{paddle_version}', "
                "currently it is recommended to use release 2.6 or develop version."
            )
    else:
        paddle_version = f"develop({paddle.version.commit[:7]})"

    logger.info(f"Using paddlepaddle {paddle_version}")

    num_timestamps = args.num_timestamps
    # create predictor
    predictor = YingLong(
        args.model_file, args.params_file, args.mean_path, args.std_path
    )

    # load data
    # HRRR Crop use 69 atmospheric variable，their index in the dataset is from 0 to 68.
    # The variable name is "z50", "z100",  "z150", "z200", "z250", "z300", "z400", "z500",
    # "z600", "z700",  "z850", "z925", "z1000", "t50", "t100", "t150", "t200", "t250",
    # "t300", "t400", "t500", "t600", "t700", "t850", "t925", "t1000", "s50", "s100",
    # "s150", "s200",  "s250", "s300", "s400", "s500", "s600", "s700", "s850", "s925",
    # "s1000", "u50", "u100", "u150", "u200", "u250", "u300", "u400", "u500", "u600",
    # "u700", "u850", "u925", "u1000", "v50", "v100", "v150", "v200", "v250", "v300",
    # "v400", "v500", "v600", "v700", "v850", "v925", "v1000",  "mslp", "u10", "v10",
    # "t2m",
    input_file = h5py.File(args.input_file, "r")["fields"]
    nwp_file = h5py.File(args.nwp_file, "r")["fields"]

    # input_data.shape: (1, 69, 440, 408)
    input_data = input_file[0:1]
    # nwp_data.shape: # (num_timestamps, 69, 440, 408)
    nwp_data = nwp_file[0:num_timestamps]
    # ground_truth.shape: (num_timestamps, 69, 440, 408)
    ground_truth = input_file[1 : num_timestamps + 1]

    # create time stamps
    cur_time = pd.to_datetime(args.init_time, format="%Y/%m/%d/%H")
    time_stamps = [[cur_time]]
    for _ in range(num_timestamps):
        cur_time += pd.Timedelta(hours=1)
        time_stamps.append([cur_time])

    # run predictor
    pred_data = predictor(input_data, time_stamps, nwp_data)
    pred_data = pred_data.squeeze(axis=1)  # (num_timestamps, 69, 440, 408)

    # save predict data
    save_path = osp.join(args.output_path, "result.npy")
    np.save(save_path, pred_data)
    logger.info(f"Save output to {save_path}")

    # plot wind data
    u10_idx, v10_idx = 66, 67
    pred_wind = (pred_data[:, u10_idx] ** 2 + pred_data[:, v10_idx] ** 2) ** 0.5
    ground_truth_wind = (
        ground_truth[:, u10_idx] ** 2 + ground_truth[:, v10_idx] ** 2
    ) ** 0.5
    data_dict = {}
    visu_keys = []
    for i in range(num_timestamps):
        visu_key = f"Init time: {args.init_time}h\n Ground truth: {i+1}h"
        visu_keys.append(visu_key)
        data_dict[visu_key] = ground_truth_wind[i]
        visu_key = f"Init time: {args.init_time}h\n YingLong-24 Layers: {i+1}h"
        visu_keys.append(visu_key)
        data_dict[visu_key] = pred_wind[i]

    save_plot_weather_from_dict(
        foldername=args.output_path,
        data_dict=data_dict,
        visu_keys=visu_keys,
        xticks=np.linspace(0, 407, 7),
        xticklabels=[str(i) for i in range(0, 409, 68)],
        yticks=np.linspace(0, 439, 9),
        yticklabels=[str(i) for i in range(0, 441, 55)],
        vmin=0,
        vmax=15,
        colorbar_label="m/s",
        num_timestamps=12,  # only plot 12 timestamps
    )
    logger.info(f"Save plot to {args.output_path}")


if __name__ == "__main__":
    main()
