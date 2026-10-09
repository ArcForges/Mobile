// SPDX-License-Identifier: Apache-2.0
using System.Buffers.Binary;
using System.Globalization;
using System.Text;
using Google.Protobuf;

namespace ArcForges.Mobile.Tests.Fixtures;

/// <summary>Encodes and decodes the gRPC-Web binary framing used by the loopback fixtures.</summary>
internal static class GrpcWebFrames
{
    private const byte DataFlag = 0x00;
    private const byte TrailerFlag = 0x80;

    /// <summary>A message frame carrying <paramref name="payload"/>.</summary>
    public static byte[] Data(byte[] payload) => Frame(DataFlag, payload);

    /// <summary>A message frame carrying the protobuf encoding of <paramref name="message"/>.</summary>
    public static byte[] Message(IMessage message) => Data(message.ToByteArray());

    /// <summary>A trailer frame whose block is the given <c>name: value</c> lines.</summary>
    public static byte[] Trailers(params string[] lines)
    {
        var block = new StringBuilder();
        foreach (var line in lines)
        {
            block.Append(line).Append("\r\n");
        }

        return Frame(TrailerFlag, Encoding.ASCII.GetBytes(block.ToString()));
    }

    /// <summary>Concatenates frames into one body.</summary>
    public static byte[] Concat(params byte[][] parts)
    {
        var total = parts.Sum(part => part.Length);
        var result = new byte[total];
        var offset = 0;
        foreach (var part in parts)
        {
            part.CopyTo(result, offset);
            offset += part.Length;
        }

        return result;
    }

    /// <summary>Parses a body into its frames. Throws when the framing is malformed.</summary>
    public static IReadOnlyList<(byte Flag, byte[] Payload)> Parse(byte[] body)
    {
        var frames = new List<(byte, byte[])>();
        var offset = 0;
        while (offset < body.Length)
        {
            if (body.Length - offset < 5)
            {
                throw new FormatException("A gRPC-Web frame header is truncated.");
            }

            var flag = body[offset];
            var length = BinaryPrimitives.ReadUInt32BigEndian(body.AsSpan(offset + 1, 4));
            offset += 5;
            if (length > body.Length - offset)
            {
                throw new FormatException("A gRPC-Web frame payload is truncated.");
            }

            frames.Add((flag, body[offset..(offset + (int)length)]));
            offset += (int)length;
        }

        return frames;
    }

    /// <summary>The payload of the single message frame in <paramref name="body"/>.</summary>
    public static byte[] SingleMessagePayload(byte[] body)
    {
        var frames = Parse(body);
        if (frames.Count != 1 || frames[0].Flag != DataFlag)
        {
            throw new FormatException("The request must carry exactly one message frame.");
        }

        return frames[0].Payload;
    }

    /// <summary>Converts a grpc-timeout header value (an ASCII integer and a unit) to milliseconds.</summary>
    public static double TimeoutMilliseconds(string header)
    {
        if (header.Length < 2 || !char.IsAsciiDigit(header[0]))
        {
            throw new FormatException($"Malformed grpc-timeout: {header}");
        }

        var unit = header[^1];
        var value = double.Parse(header[..^1], NumberStyles.None, CultureInfo.InvariantCulture);
        return unit switch
        {
            'H' => value * 3_600_000,
            'M' => value * 60_000,
            'S' => value * 1_000,
            'm' => value,
            'u' => value / 1_000,
            'n' => value / 1_000_000,
            _ => throw new FormatException($"Unknown grpc-timeout unit: {header}"),
        };
    }

    private static byte[] Frame(byte flag, byte[] payload)
    {
        var frame = new byte[5 + payload.Length];
        frame[0] = flag;
        BinaryPrimitives.WriteUInt32BigEndian(frame.AsSpan(1, 4), (uint)payload.Length);
        payload.CopyTo(frame, 5);
        return frame;
    }
}
